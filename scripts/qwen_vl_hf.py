#!/usr/bin/env python3
"""
Qwen VL 推理 — transformers 版本 (fallback, 无需 vLLM)
用法: python qwen_vl_hf.py --corpus /tmp/eg_30_corpus --out /tmp/qwen_out --batch 4
"""
import json, os, time, argparse, glob
from pathlib import Path
from PIL import Image
import torch
from figure_classifier import classify_figure  # 使用共享分类器，避免本地副本行为分歧

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
                # clean img_caption (MinerU wraps in list-str)
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
    ap.add_argument('--batch', type=int, default=4)
    ap.add_argument('--max', type=int, default=0)
    ap.add_argument('--papers', default='', help='comma-sep paper_ids')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    jsonl_path = os.path.join(args.out, 'qwen_vl_results.jsonl')
    tasks = [t.strip() for t in args.tasks.split(',') if t.strip()]

    items = find_blocks(args.corpus, tasks)
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

    print(f'Loading Qwen2.5-VL from {args.model}...')
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
    from qwen_vl_utils import process_vision_info

    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, device_map='auto'
    )
    processor = AutoProcessor.from_pretrained(args.model)
    processor.tokenizer.padding_side = "left"
    print(f'Model loaded. Processing {len(todo)} blocks (batch={args.batch})...')

    t0 = time.time()
    ok = 0

    with open(jsonl_path, 'a', encoding='utf-8') as f_out:
        for s in range(0, len(todo), args.batch):
            chunk = todo[s:s+args.batch]
            messages_batch = []
            for it in chunk:
                messages_batch.append([{
                    'role': 'user',
                    'content': [
                        {'type': 'image', 'image': it['image_path']},
                        {'type': 'text', 'text': PROMPTS[it['task']]},
                    ],
                }])

            try:
                texts = [processor.apply_chat_template(m, tokenize=False, add_generation_prompt=True)
                         for m in messages_batch]
                image_inputs, video_inputs = process_vision_info(
                    [m for msgs in messages_batch for m in msgs]
                )
                inputs = processor(
                    text=texts,
                    images=image_inputs,
                    videos=video_inputs,
                    padding=True,
                    return_tensors='pt',
                ).to(model.device)

                with torch.no_grad():
                    gen_ids = model.generate(**inputs, max_new_tokens=1024)
                gen_ids_trimmed = [
                    out[len(inp):] for inp, out in zip(inputs.input_ids, gen_ids)
                ]
                outputs = processor.batch_decode(gen_ids_trimmed, skip_special_tokens=True,
                                                  clean_up_tokenization_spaces=False)

                for it, text in zip(chunk, outputs):
                    rec = dict(it)
                    rec['status'] = 'ok' if text else 'empty'
                    rec['output'] = text.strip()
                    rec['n_chars'] = len(text)
                    if it['task'] == 'image' and text:
                        import re
                        m = re.search(r'\{[\s\S]*\}', text)
                        if m:
                            try:
                                parsed = json.loads(m.group())
                                ft = parsed.get('figure_type', '')
                                cap = parsed.get('title_or_caption', '') or ''
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
                print(f'  Batch error: {e}')
                for it in chunk:
                    rec = dict(it); rec['status'] = f'error:{e}'; rec['output'] = None
                    f_out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                f_out.flush()

            done_so_far = s + len(chunk)
            elapsed = time.time() - t0
            rate = done_so_far / elapsed
            eta = (len(todo) - done_so_far) / rate if rate > 0 else 0
            print(f'  {done_so_far}/{len(todo)} | {rate:.1f} img/s | ETA {eta:.0f}s', end='\r')

    elapsed = time.time() - t0
    print(f'\nDone: {ok}/{len(todo)} ok in {elapsed:.1f}s ({ok/elapsed:.2f} img/s)')

if __name__ == '__main__':
    main()
