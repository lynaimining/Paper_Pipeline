#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qwen_vl_extract.py — Qwen2.5-VL-7B 串联 MinerU 产物做视觉理解

链路: PDF → MinerU(content_list.json + 切图) → 本脚本按 type 分派 → Qwen2.5-VL → 增量落盘

分派策略 (--tasks 控制启用哪些):
  table  : type=table 的图 → 输出 HTML 表格 (对标/替代 GOT-OCR)
  image  : type=image 的图 → 输出图表/地图的结构化视觉描述
  page   : MinerU 解析疑似失败的页(整页图)→ 整页识别兜底

输出: <out>/qwen_vl_results.jsonl (增量, 以 uid 去重) + qwen_vl_results.parquet
沿用 batch_table_ocr.py 的字段约定 (paper_id / block_idx / image_basename)。
"""
import json, os, glob, time, argparse, base64
from pathlib import Path

# ── 默认配置 ──
DEFAULT_CORPUS = '/root/autodl-tmp/Natural Resources Research/2024'
DEFAULT_OUT = '/root/autodl-tmp/qwen_vl_2024'
DEFAULT_MODEL = '/root/autodl-tmp/models/Qwen/Qwen2.5-VL-7B-Instruct'

# ── 各任务的 prompt ──
PROMPTS = {
    'table': (
        "This is a table image from a geology research paper. "
        "Recognize the table and output it as a clean, well-structured HTML <table>. "
        "Preserve the exact row/column structure, merged cells (use rowspan/colspan), "
        "headers (<th>), numeric values, units and superscripts/subscripts. "
        "Output ONLY the HTML <table>...</table>, nothing else."
    ),
    'image': (
        "This is a figure from a geology research paper (e.g. geological map, scatter plot, "
        "bar chart, cross-section, or photomicrograph). Analyze it and return a JSON object with keys: "
        '{"figure_type": str, "title_or_caption": str|null, "axes": {"x":str|null,"y":str|null}|null, '
        '"legend": [str], "key_values": [str], "trends_or_findings": [str], "text_in_figure": [str]}. '
        "Extract any numeric values, ranges, sample names, rock/mineral names visible in the figure. "
        "Output ONLY the JSON object."
    ),
    'page': (
        "This is a full page from a geology research paper that may contain mixed text, tables and figures. "
        "Transcribe all readable content into clean Markdown, preserving headings, paragraphs, "
        "tables (as Markdown tables) and figure captions. Output ONLY the Markdown."
    ),
}


def find_blocks(corpus_root, tasks):
    """扫 *_content_list.json, 按启用的 task 类型收集待处理块。返回 list[dict]。"""
    type_map = {'table': 'table', 'image': 'image'}  # page 走不同逻辑
    want_types = {type_map[t] for t in tasks if t in type_map}
    items = []
    cls = sorted(glob.glob(os.path.join(corpus_root, '**', 'auto', '*_content_list.json'),
                           recursive=True))
    for cl in cls:
        try:
            data = json.load(open(cl, encoding='utf-8'))
        except Exception:
            continue
        folder = os.path.dirname(cl)
        paper_id = os.path.normpath(cl).split(os.sep)[-3]
        for idx, b in enumerate(data):
            btype = b.get('type')
            if btype in want_types:
                img = b.get('img_path', '')
                full = os.path.join(folder, img) if img else ''
                if full and os.path.exists(full):
                    items.append({
                        'uid': f'{paper_id}::{idx}::{os.path.basename(full)}',
                        'paper_id': paper_id,
                        'block_idx': idx,
                        'task': btype,            # 'table' or 'image'
                        'image_path': full,
                        'image_basename': os.path.basename(full),
                    })
    return items


def load_done(jsonl_path):
    done = set()
    if os.path.exists(jsonl_path):
        for line in open(jsonl_path, encoding='utf-8'):
            try:
                done.add(json.loads(line)['uid'])
            except Exception:
                pass
    return done


def build_messages(task, image_path):
    """构造 Qwen2.5-VL 的 chat messages (vLLM 0.11.0 用 image_pil 传 PIL 对象)。"""
    from PIL import Image
    img = Image.open(image_path).convert('RGB')
    return [{
        'role': 'user',
        'content': [
            {'type': 'image_pil', 'image_pil': img},
            {'type': 'text', 'text': PROMPTS[task]},
        ],
    }]


def run(args):
    from vllm import LLM, SamplingParams

    tasks = args.tasks.split(',')
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    jsonl_path = os.path.join(out_dir, 'qwen_vl_results.jsonl')
    parquet_path = os.path.join(out_dir, 'qwen_vl_results.parquet')

    print('='*60)
    print(f'Step 1: 扫 MinerU content_list, 任务={tasks}')
    print('='*60)
    items = find_blocks(args.corpus, tasks)
    # page 任务: 暂以 image 块的整页兜底留待后续; 当前先支持 table/image
    done = load_done(jsonl_path)
    todo = [it for it in items if it['uid'] not in done]
    if args.papers:
        keep = set(args.papers.split(','))
        todo = [it for it in todo if it['paper_id'] in keep]
    if args.max:
        todo = todo[:args.max]
    print(f'  候选块 {len(items)}, 已完成 {len(done)}, 本次待处理 {len(todo)}')
    if not todo:
        print('无待处理项。'); return

    print('='*60)
    print('Step 2: 加载 Qwen2.5-VL (vLLM 离线)')
    print('='*60)
    llm = LLM(
        model=args.model,
        gpu_memory_utilization=args.gpu_mem,
        max_model_len=args.max_len,
        limit_mm_per_prompt={'image': 1},
        dtype='bfloat16',
        trust_remote_code=True,
    )
    sp = SamplingParams(temperature=0.0, max_tokens=args.max_tokens, repetition_penalty=1.05)

    print('='*60)
    print(f'Step 3: 推理 {len(todo)} 块')
    print('='*60)
    t0 = time.time()
    # 按 task 分组批处理 (同 task 共用 prompt, 利于吞吐)
    f_out = open(jsonl_path, 'a', encoding='utf-8')
    BATCH = args.batch
    ok = 0
    for s in range(0, len(todo), BATCH):
        chunk = todo[s:s+BATCH]
        msgs = [build_messages(it['task'], it['image_path']) for it in chunk]
        try:
            outs = llm.chat(msgs, sp)
        except Exception as e:
            for it in chunk:
                rec = dict(it); rec['status'] = f'error:{type(e).__name__}'; rec['output'] = None
                f_out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f_out.flush(); continue
        for it, o in zip(chunk, outs):
            text = o.outputs[0].text.strip()
            rec = dict(it)
            rec['status'] = 'ok' if text else 'empty'
            rec['output'] = text
            rec['n_chars'] = len(text)
            # 解析 Qwen 输出并写入 figure_type / category 字段（image任务）
            if it['task'] == 'image' and text:
                try:
                    import re as _re, json as _json
                    m = _re.search(r'\{[\s\S]*\}', text)
                    if m:
                        parsed = _json.loads(m.group())
                        raw_ft = parsed.get('figure_type', '')
                        caption = parsed.get('title_or_caption', '') or ''
                        # 调用 figure_classifier 确定 category
                        from figure_classifier import classify_figure
                        rec['figure_type'] = raw_ft
                        rec['category'] = classify_figure(raw_ft, caption)
                        rec['caption'] = caption
                except Exception:
                    pass
            f_out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            if text: ok += 1
        f_out.flush()
        el = time.time() - t0
        sp_ = (s+len(chunk))/el if el>0 else 0
        eta = (len(todo)-s-len(chunk))/sp_ if sp_>0 else 0
        print(f'  [{s+len(chunk)}/{len(todo)}] ok={ok} {sp_:.2f} blk/s ETA={eta/60:.1f}min')
    f_out.close()
    print(f'\n完成! 耗时 {(time.time()-t0)/60:.1f}min, ok={ok}/{len(todo)}')

    # 汇总 parquet
    try:
        import pandas as pd
        rows = [json.loads(l) for l in open(jsonl_path, encoding='utf-8') if l.strip()]
        pd.DataFrame(rows).to_parquet(parquet_path, index=False)
        print(f'Parquet: {parquet_path} ({len(rows)} 行)')
    except Exception as e:
        print(f'parquet 汇总跳过: {e}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', default=DEFAULT_CORPUS)
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--model', default=DEFAULT_MODEL)
    ap.add_argument('--tasks', default='table,image', help='逗号分隔: table,image,page')
    ap.add_argument('--papers', default='', help='逗号分隔 paper_id, 只跑这些(小批量试跑用)')
    ap.add_argument('--max', type=int, default=0, help='最多处理 N 块')
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--gpu-mem', type=float, default=0.93)
    ap.add_argument('--max-len', type=int, default=8192)
    ap.add_argument('--max-tokens', type=int, default=2048)
    args = ap.parse_args()
    run(args)


if __name__ == '__main__':
    main()
