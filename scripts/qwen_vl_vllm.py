#!/usr/bin/env python3
"""
Qwen VL 推理 — vLLM 版本（高吞吐）
接口与 qwen_vl_hf.py 完全兼容，直接替换即可。

vLLM 优势：
  - PagedAttention：KV cache 利用率更高
  - Continuous batching：无需等待整批完成，随到随处理
  - 实测比 HuggingFace 快 2-4x（同 batch size）

用法: python qwen_vl_vllm.py --corpus /tmp/corpus --out /tmp/out --batch 32
"""
import json, os, time, argparse, glob, re, sys
from pathlib import Path

MODEL_PATH = '/root/autodl-tmp/models/qwen/Qwen2.5-VL-7B-Instruct'

PROMPTS = {
    'image': (
        "This is a figure from a geology research paper. Analyze it and return a JSON object with keys: "
        '{"figure_type": str, "title_or_caption": str|null, "axes": {"x":str|null,"y":str|null}|null, '
        '"legend": [str], "key_values": [str], "trends_or_findings": [str], "text_in_figure": [str]}. '
        "Extract numeric values, rock/mineral names visible in the figure. "
        "Output ONLY the JSON object."
    ),
    'table': (
        "This is a table image from a geology research paper. "
        "Recognize the table and output it as clean HTML <table>...</table>. "
        "Preserve row/column structure, headers, numeric values and units. "
        "Output ONLY the HTML."
    ),
}


def find_blocks(corpus_root, tasks=('image', 'table')):
    want = set(tasks)
    items = []
    for cl in sorted(glob.glob(os.path.join(corpus_root, '**', 'auto', '*_content_list.json'), recursive=True)):
        try:
            with open(cl, encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception:
            continue
        folder = os.path.dirname(cl)
        paper_id = os.path.normpath(cl).split(os.sep)[-3]
        for idx, b in enumerate(data):
            btype = b.get('type')
            if btype not in want:
                continue
            img = b.get('img_path', '')
            full = os.path.join(folder, img) if img else ''
            if full and os.path.exists(full):
                raw_cap = b.get('img_caption', '') or ''
                if isinstance(raw_cap, str) and raw_cap.startswith('['):
                    import ast
                    try: raw_cap = ' '.join(ast.literal_eval(raw_cap))
                    except Exception: pass
                cap_text = str(raw_cap).strip().strip("'[]\"'")
                items.append({
                    'uid': f'{paper_id}::{idx}::{os.path.basename(full)}',
                    'paper_id': paper_id, 'block_idx': idx,
                    'task': btype, 'image_path': full,
                    'image_basename': os.path.basename(full),
                    'img_caption': cap_text,
                })
    return items


def load_done(path):
    done = set()
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)['uid'])
                except Exception:
                    pass
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--model', default=MODEL_PATH)
    ap.add_argument('--tasks', default='image')
    ap.add_argument('--batch', type=int, default=32,
                    help='vLLM 下等同于 max_num_seqs，建议 32-64')
    ap.add_argument('--max', type=int, default=0)
    ap.add_argument('--papers', default='', help='comma-sep paper_ids')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    jsonl_path = os.path.join(args.out, 'qwen_vl_results.jsonl')
    tasks_list = [t.strip() for t in args.tasks.split(',') if t.strip()]

    items = find_blocks(args.corpus, tasks_list)
    done = load_done(jsonl_path)
    todo = [it for it in items if it['uid'] not in done]
    if args.papers:
        keep = set(args.papers.split(','))
        todo = [it for it in todo if it['paper_id'] in keep]
    if args.max:
        todo = todo[:args.max]
    print(f'Blocks: {len(items)} total, {len(done)} done, {len(todo)} to process')
    if not todo:
        print('Nothing to do.'); return

    # ── 加载 vLLM ────────────────────────────────────────────────────────────
    try:
        from vllm import LLM, SamplingParams
    except ImportError:
        print('[ERROR] vllm 未安装，请先运行: pip install vllm', file=sys.stderr)
        sys.exit(1)

    from PIL import Image
    from transformers import AutoProcessor
    from figure_classifier import classify_figure

    print(f'Loading Qwen2.5-VL via vLLM from {args.model}...')
    processor = AutoProcessor.from_pretrained(args.model)
    llm = LLM(
        model=args.model,
        dtype='bfloat16',
        max_num_seqs=args.batch,
        max_model_len=8192,
        gpu_memory_utilization=0.90,
        attention_backend="TRITON_ATTN",
        limit_mm_per_prompt={'image': 1},
        trust_remote_code=True,
    )
    sampling = SamplingParams(temperature=0.0, max_tokens=1024)
    print(f'vLLM loaded. Processing {len(todo)} blocks (max_num_seqs={args.batch})...')

    t0 = time.time()
    ok = 0

    with open(jsonl_path, 'a', encoding='utf-8') as f_out:
        chunk_size = args.batch * 4

        for chunk_start in range(0, len(todo), chunk_size):
            chunk = todo[chunk_start:chunk_start + chunk_size]

            prompts = []
            for it in chunk:
                img = Image.open(it['image_path']).convert('RGB')
                msgs = [{'role': 'user', 'content': [
                    {'type': 'image', 'image': img},
                    {'type': 'text', 'text': PROMPTS[it['task']]},
                ]}]
                text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                prompts.append({'prompt': text, 'multi_modal_data': {'image': img}})

            try:
                outputs = llm.generate(prompts, sampling)
                for it, out in zip(chunk, outputs):
                    text = out.outputs[0].text.strip()
                    rec = dict(it)
                    rec['status'] = 'ok' if text else 'empty'
                    rec['output'] = text
                    rec['n_chars'] = len(text)

                    if it['task'] == 'image' and text:
                        m = re.search(r'\{[\s\S]*\}', text)
                        if m:
                            try:
                                parsed = json.loads(m.group())
                                ft = parsed.get('figure_type', '')
                                cap_raw = parsed.get('title_or_caption', '') or ''
                                cap = cap_raw if isinstance(cap_raw, str) else ' '.join(str(x) for x in cap_raw) if isinstance(cap_raw, list) else ''
                                rec['figure_type'] = ft
                                rec['caption'] = cap
                                rec['legend'] = parsed.get('legend', [])
                                rec['text_in_figure'] = parsed.get('text_in_figure', [])
                                rec['category'] = classify_figure(ft, cap)
                            except Exception:
                                pass

                    f_out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    ok += 1
                f_out.flush()
            except Exception as e:
                print(f'\n  Chunk error: {e}')
                for it in chunk:
                    rec = dict(it); rec['status'] = f'error:{e}'; rec['output'] = None
                    f_out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                f_out.flush()

            done_so_far = chunk_start + len(chunk)
            elapsed = time.time() - t0
            rate = done_so_far / elapsed if elapsed > 0 else 0
            eta = (len(todo) - done_so_far) / rate if rate > 0 else 0
            print(f'  {done_so_far}/{len(todo)} | {rate:.2f} img/s | ETA {eta:.0f}s', end='\r')

    elapsed = time.time() - t0
    print(f'\nDone: {ok}/{len(todo)} ok in {elapsed:.1f}s ({ok/elapsed:.2f} img/s)')


if __name__ == '__main__':
    main()
