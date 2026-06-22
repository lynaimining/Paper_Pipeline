#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_visual.py — 把 Qwen VL 识别结果注入 MinerU .md，供 DeepSeek 读取

逻辑:
  1. 读 qwen_vl_results.jsonl (Qwen 对图/表的识别输出)
  2. 按 paper_id 分组
  3. 对每篇论文的 .md 文件, 找 ![](images/xxx.jpg) 占位符
  4. 如果该图片有 Qwen 识别结果, 把占位符替换为实际内容
  5. 输出增强后的 .md 到 <out>/<paper_id>.md (不改原文件)

输出格式:
  - table → 替换为 "<!-- TABLE -->\n<实际HTML表格>\n<!-- /TABLE -->"
  - image → 替换为 "<!-- FIGURE -->\n<视觉描述JSON>\n<!-- /FIGURE -->"

这样 DeepSeek 读增强 .md 时能看到完整的图表内容。
"""
import json, os, re, glob, argparse
from pathlib import Path


def load_qwen_results(jsonl_path):
    """加载 Qwen VL 结果, 返回 {paper_id: {image_basename: record}}"""
    lookup = {}
    for line in open(jsonl_path, 'r', encoding='utf-8'):
        try:
            r = json.loads(line)
        except Exception:
            continue
        pid = r.get('paper_id', '')
        basename = r.get('image_basename', '')
        if pid and basename and r.get('status') == 'ok':
            lookup.setdefault(pid, {})[basename] = r
    return lookup


def inject_one(md_path, paper_id, img_results):
    """对一篇 .md 注入 Qwen 结果, 返回增强后的文本"""
    text = open(md_path, 'r', encoding='utf-8').read()

    def replacer(m):
        img_ref = m.group(0)  # ![](images/xxx.jpg)
        # 提取文件名
        fname_match = re.search(r'images/([^)]+)', img_ref)
        if not fname_match:
            return img_ref
        fname = fname_match.group(1)
        rec = img_results.get(fname)
        if not rec or not rec.get('output'):
            return img_ref  # 无识别结果, 保留原占位符

        task = rec.get('task', 'image')
        output = rec['output'].strip()
        # 去掉 ```html / ```json 包裹
        output = re.sub(r'^```(?:html|json)\s*\n?', '', output)
        output = re.sub(r'\n?```\s*$', '', output)

        if task == 'table':
            return f"<!-- TABLE: {fname} -->\n{output}\n<!-- /TABLE -->"
        else:
            return f"<!-- FIGURE: {fname} -->\n{output}\n<!-- /FIGURE -->"

    enhanced = re.sub(r'!\[(?:[^\]]*)\]\(images/[^)]+\)', replacer, text)
    return enhanced


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', default='/root/autodl-tmp/Natural Resources Research/2024')
    ap.add_argument('--qwen-results', default='/root/autodl-tmp/qwen_vl_2024/qwen_vl_results.jsonl')
    ap.add_argument('--out', default='/root/autodl-tmp/enhanced_md_2024')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    lookup = load_qwen_results(args.qwen_results)
    print(f'Qwen 结果: {sum(len(v) for v in lookup.values())} 条, 覆盖 {len(lookup)} 篇论文')

    # 找所有 .md
    mds = sorted(glob.glob(os.path.join(args.corpus, '**', 'auto', '*.md'), recursive=True))
    mds = [m for m in mds if '_layout' not in m and '_middle' not in m
           and '_model' not in m and '_spans' not in m]

    injected = 0
    for md in mds:
        paper_id = Path(md).stem
        img_results = lookup.get(paper_id, {})
        if not img_results:
            # 无 Qwen 结果, 直接复制原文
            enhanced = open(md, 'r', encoding='utf-8').read()
        else:
            enhanced = inject_one(md, paper_id, img_results)
            injected += 1

        out_path = os.path.join(args.out, f'{paper_id}.md')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(enhanced)

    print(f'完成: {len(mds)} 篇 .md → {args.out}/')
    print(f'  其中 {injected} 篇注入了 Qwen 视觉内容')


if __name__ == '__main__':
    main()
