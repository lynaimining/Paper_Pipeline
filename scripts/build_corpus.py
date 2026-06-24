#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_corpus.py — 生成 E_corpus/

对 _source/text/ 里的论文 markdown 做清洗，输出 DAPT 预训练语料。

清洗策略（B+ 级）：
  ✅ 删除图像占位符  ![...](...) / ![][ref]
  ✅ HTML 表格 → 提取纯文本（保留数值，去掉 HTML 标签）
  ✅ 页眉页脚启发式过滤（卷期号、DOI、页码、Received/Accepted 行）
  ✅ 连续空行压缩（≥3行 → 2行）
  ✅ 保留 LaTeX 公式（$$...$$、$...$）
  ❌ 不做多栏断句修复（收益低于成本）

输出:
  E_corpus/
  ├── papers_clean.jsonl   每行 {paper_id, text, n_chars, n_tokens_est}
  └── corpus_stats.json    总量统计

用法:
  python build_corpus.py --source-dir dataset/_source --output-dir dataset
  python build_corpus.py --source-dir dataset/_source --output-dir dataset --workers 8
"""
import argparse
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path


# ── HTML 表格文本提取 ─────────────────────────────────────────────────────────

class _TableTextExtractor(HTMLParser):
    """把 HTML 表格解析为空格/换行分隔的纯文本。"""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._in_cell = False
        self._cell_buf: list[str] = []
        self._row_cells: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("td", "th"):
            self._in_cell = True
            self._cell_buf = []
        elif tag == "tr":
            self._row_cells = []

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._in_cell = False
            self._row_cells.append(" ".join(self._cell_buf).strip())
        elif tag == "tr":
            line = "  ".join(c for c in self._row_cells if c)
            if line:
                self._parts.append(line)

    def handle_data(self, data):
        if self._in_cell:
            s = data.strip()
            if s:
                self._cell_buf.append(s)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def _extract_html_table(html_block: str) -> str:
    extractor = _TableTextExtractor()
    try:
        extractor.feed(html_block)
        return extractor.get_text()
    except Exception:
        # 解析失败则返回空字符串，宁可丢弃也不保留 HTML 噪音
        return ""


# ── 页眉页脚启发式过滤 ────────────────────────────────────────────────────────

_HEADER_FOOTER_PATTERNS = [
    re.compile(r"^\s*v\.\s*\d+.*?pp?\.\s*\d+", re.IGNORECASE),   # v. 93, pp. 1234
    re.compile(r"^\s*doi\s*:", re.IGNORECASE),                     # doi: 10.xxxx
    re.compile(r"^\s*https?://doi\.org/", re.IGNORECASE),
    re.compile(r"^\s*received\s+\w+\s+\d+", re.IGNORECASE),       # Received March 15
    re.compile(r"^\s*accepted\s+\w+\s+\d+", re.IGNORECASE),       # Accepted July 2
    re.compile(r"^\s*©\s*\d{4}", re.IGNORECASE),                   # © 1998
    re.compile(r"^\s*copyright\s+\d{4}", re.IGNORECASE),
    re.compile(r"^\s*\d{4}\s*$"),                                   # 纯年份行
    re.compile(r"^\s*[-—–]\s*\d+\s*[-—–]\s*$"),                   # — 1236 —
    re.compile(r"^\s*\d+\s*$"),                                     # 纯页码（单独成行）
    re.compile(r"^\s*economic\s+geology\b", re.IGNORECASE),        # 期刊名行
    re.compile(r"^\s*mineralium\s+deposita\b", re.IGNORECASE),
    re.compile(r"^\s*ore\s+geology\s+reviews\b", re.IGNORECASE),
    re.compile(r"^\s*journal\s+of\s+geochemical", re.IGNORECASE),
]


def _is_header_footer(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) > 120:        # 正文行通常更长
        return False
    return any(p.search(stripped) for p in _HEADER_FOOTER_PATTERNS)


# ── 主清洗函数 ────────────────────────────────────────────────────────────────

# 图像占位符：![alt](path) 或 ![][ref] 或 ![](path)
_IMG_RE = re.compile(r"!\[.*?\]\(.*?\)|!\[.*?\]\[.*?\]|!\[\]\[.*?\]")

# HTML 块：<html>...</html>（MinerU 表格输出）
_HTML_BLOCK_RE = re.compile(r"<html>.*?</html>", re.DOTALL | re.IGNORECASE)

# 连续空行（3行以上压缩为2行）
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def clean_markdown(text: str) -> str:
    """对 MinerU markdown 做 B+ 级清洗，返回清洗后文本。"""

    # 1. HTML 表格 → 提取文本
    def _replace_html(m: re.Match) -> str:
        extracted = _extract_html_table(m.group(0))
        return f"\n{extracted}\n" if extracted else "\n"

    text = _HTML_BLOCK_RE.sub(_replace_html, text)

    # 2. 删除图像占位符
    text = _IMG_RE.sub("", text)

    # 3. 页眉页脚过滤（逐行）
    lines = text.splitlines()
    lines = [l for l in lines if not _is_header_footer(l)]
    text = "\n".join(lines)

    # 4. 压缩连续空行
    text = _MULTI_BLANK_RE.sub("\n\n", text)

    return text.strip()


# ── 估算 token 数（粗略：字符数 / 4）────────────────────────────────────────

def _est_tokens(text: str) -> int:
    return len(text) // 4


# ── 单篇处理（用于 ProcessPoolExecutor）──────────────────────────────────────

def _process_one(md_path_str: str) -> dict | None:
    md_path = Path(md_path_str)
    paper_id = md_path.stem
    try:
        raw = md_path.read_text(encoding="utf-8")
        # 截到 References 前（与 deepseek_extract 一致）
        for marker in ["# References", "# REFERENCES", "## References", "## REFERENCES"]:
            idx = raw.find(marker)
            if idx > 0:
                raw = raw[:idx]
                break
        cleaned = clean_markdown(raw)
        if len(cleaned) < 200:     # 过短视为解析失败
            return None
        return {
            "paper_id":      paper_id,
            "text":          cleaned,
            "n_chars":       len(cleaned),
            "n_tokens_est":  _est_tokens(cleaned),
        }
    except Exception as e:
        print(f"  [WARN] {paper_id}: {e}", file=sys.stderr)
        return None


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="生成 E_corpus/ DAPT 预训练语料")
    parser.add_argument("--source-dir", required=True, help="_source/ 目录")
    parser.add_argument("--output-dir", required=True, help="输出根目录")
    parser.add_argument("--workers", type=int, default=4,
                        help="并行进程数（默认 4，纯 CPU IO）")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    text_dir   = source_dir / "text"
    out_dir    = Path(args.output_dir) / "E_corpus"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not text_dir.exists():
        print(f"[ERROR] text/ 目录不存在: {text_dir}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(text_dir.glob("*.md"))
    if not md_files:
        print(f"[ERROR] text/ 目录里没有 .md 文件", file=sys.stderr)
        sys.exit(1)

    print(f"共 {len(md_files)} 篇，{args.workers} workers 并行清洗...")

    out_path = out_dir / "papers_clean.jsonl"
    total_chars = total_tokens = ok = skipped = 0

    # 先并行处理，再按 paper_id 排序写出（保证可复现顺序）
    results_map: dict[str, dict] = {}

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_process_one, str(p)): p.stem
            for p in md_files
        }
        for fut in as_completed(futures):
            paper_id = futures[fut]
            result = fut.result()
            if result is None:
                skipped += 1
            else:
                results_map[paper_id] = result

    with open(out_path, "w", encoding="utf-8") as fout:
        for paper_id in sorted(results_map):
            result = results_map[paper_id]
            fout.write(json.dumps(result, ensure_ascii=False) + "\n")
            total_chars  += result["n_chars"]
            total_tokens += result["n_tokens_est"]
            ok += 1

    # ── stats ─────────────────────────────────────────────────────────────────
    stats = {
        "n_papers":       ok,
        "n_skipped":      skipped,
        "total_chars":    total_chars,
        "total_tokens_est": total_tokens,
        "avg_chars_per_paper": total_chars // ok if ok else 0,
        "cleaning_rules": [
            "html_table_to_text",
            "remove_image_placeholders",
            "heuristic_header_footer_filter",
            "compress_blank_lines",
            "trim_references_section",
        ],
    }
    (out_dir / "corpus_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2)
    )

    print(f"\n  E 完成 → {out_dir}")
    print(f"    papers_clean.jsonl  {ok} 篇（跳过 {skipped} 篇）")
    print(f"    总字符: {total_chars:,}  估算 tokens: {total_tokens:,}")
    print(f"    corpus_stats.json")


if __name__ == "__main__":
    main()
