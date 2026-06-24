#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_extractor_train.py — 生成 C_extractor_train/

将 (论文全文 markdown → trusted JSON) 组织成 SFT 训练对，
用于训练离线抽取模型替代 DeepSeek API。

策略：
  - 输入文本：References 前的全文（复用 deepseek_extract 的 load_body 逻辑）
  - split 来源：_source/splits.json（与 A、D 共享，test 集不泄漏）
  - 格式：ShareGPT（from/value），system prompt 与 deepseek_extract 完全一致
  - 过滤：_gate_status == 'fail' 的记录不进训练集

用法:
  python build_extractor_train.py
      --source-dir dataset/_source
      --output-dir dataset
"""
import argparse
import importlib.util
import json
from pathlib import Path


# ── 加载 deepseek_extract.py 的 SYSTEM_PROMPT 常量 ────────────────────────────
_SYSTEM_PROMPT_PATH = Path(__file__).parent / "deepseek_extract.py"

def _load_system_prompt() -> str:
    """
    从 deepseek_extract.py 读取 SYSTEM_PROMPT 常量。
    先尝试 importlib 动态加载（直接得到字符串对象），
    失败时回退到文本解析（兼容无 openai 安装的环境）。
    """
    # 方法一：importlib 加载（最稳）
    try:
        spec = importlib.util.spec_from_file_location("deepseek_extract_mod", _SYSTEM_PROMPT_PATH)
        mod = importlib.util.module_from_spec(spec)
        # 拦截 async import 的副作用——只需要常量，不执行 main
        spec.loader.exec_module(mod)
        prompt = getattr(mod, "SYSTEM_PROMPT", None)
        if prompt:
            return prompt
    except Exception:
        pass

    # 方法二：文本解析回退（openai 未安装时）
    src = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    for quote in ('"""', "'''"):
        marker = f"SYSTEM_PROMPT = {quote}"
        start = src.find(marker)
        if start != -1:
            start += len(marker)
            end = src.find(quote, start)
            if end != -1:
                return src[start:end]

    raise ValueError(
        f"无法从 {_SYSTEM_PROMPT_PATH} 解析 SYSTEM_PROMPT，"
        "请检查 deepseek_extract.py 是否有该常量"
    )


def load_body(md_path: str) -> str:
    """读取论文正文，截去 References 之后的部分（与 deepseek_extract 一致）。"""
    text = Path(md_path).read_text(encoding="utf-8")
    for marker in ["# References", "# REFERENCES", "## References", "## REFERENCES"]:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]
            break
    return text.strip()


def build_record(paper_id: str, body: str, trusted: dict, system_prompt: str) -> dict:
    """构造单条 SFT 训练记录（ShareGPT 格式）。"""
    # 输出只保留 DeepSeek 原始抽取的字段，去掉 pipeline 内部字段
    _internal = {"_gate_status", "_gate_flags", "_prompt_hash", "pipeline_version"}
    output = {k: v for k, v in trusted.items() if k not in _internal}

    return {
        "id": f"ext_{paper_id}",
        "paper_id": paper_id,
        "qa_type": "extraction",
        "conversations": [
            {"from": "system", "value": system_prompt},
            {"from": "human",  "value": body},
            {"from": "gpt",    "value": json.dumps(output, ensure_ascii=False)},
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="生成 C_extractor_train/ SFT 数据")
    parser.add_argument("--source-dir", required=True, help="_source/ 目录")
    parser.add_argument("--output-dir", required=True, help="输出根目录")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    out_dir    = Path(args.output_dir) / "C_extractor_train"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 加载 splits.json ──────────────────────────────────────────────────────
    splits_path = source_dir / "splits.json"
    if not splits_path.exists():
        raise FileNotFoundError(f"splits.json 不存在: {splits_path}")
    splits_data = json.loads(splits_path.read_text())
    split_map: dict = splits_data.get("split_map", splits_data)

    # ── 加载 trusted.json ─────────────────────────────────────────────────────
    # trusted.json 由 deepseek_extract.py 写入 _source/_extract/，
    # 但也有可能被手动复制到 _source/ 下，两处都查
    trusted_path = source_dir / "trusted.json"
    if not trusted_path.exists():
        trusted_path = source_dir / "_extract" / "trusted.json"
    if not trusted_path.exists():
        raise FileNotFoundError(
            f"trusted.json 不存在，已查找:\n"
            f"  {source_dir / 'trusted.json'}\n"
            f"  {source_dir / '_extract' / 'trusted.json'}"
        )
    trusted_list = json.loads(trusted_path.read_text())
    trusted_map  = {str(r["paper_id"]): r for r in trusted_list}

    # ── 加载 system prompt ────────────────────────────────────────────────────
    system_prompt = _load_system_prompt()

    # ── text/ 目录 ────────────────────────────────────────────────────────────
    text_dir = source_dir / "text"
    if not text_dir.exists():
        raise FileNotFoundError(
            f"text/ 目录不存在: {text_dir}\n"
            "请确认 pipeline 已跑过（process_paper.py 会保存 .md 文件）"
        )

    # ── 构建训练对 ────────────────────────────────────────────────────────────
    by_split: dict[str, list] = {"train": [], "val": [], "test": []}
    skipped_no_text   = []
    skipped_no_trusted = []
    skipped_gate_fail  = []

    for md_file in sorted(text_dir.glob("*.md")):
        paper_id = md_file.stem
        trusted  = trusted_map.get(paper_id)

        if trusted is None:
            skipped_no_trusted.append(paper_id)
            continue

        if trusted.get("_gate_status") == "fail":
            skipped_gate_fail.append(paper_id)
            continue

        body = load_body(str(md_file))
        if not body:
            skipped_no_text.append(paper_id)
            continue

        split  = split_map.get(paper_id, "train")
        record = build_record(paper_id, body, trusted, system_prompt)
        by_split[split].append(record)

    # ── 写文件 ────────────────────────────────────────────────────────────────
    total = 0
    for split_name, records in by_split.items():
        if not records:
            continue
        out_path = out_dir / f"{split_name}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  C/{split_name}.jsonl  {len(records)} 条")
        total += len(records)

    print(f"\n  C 完成: {total} 条 → {out_dir}")
    if skipped_no_trusted:
        print(f"  跳过（无 trusted record）: {len(skipped_no_trusted)} 篇")
    if skipped_gate_fail:
        print(f"  跳过（gate fail）: {len(skipped_gate_fail)} 篇")
    if skipped_no_text:
        print(f"  跳过（md 为空）: {len(skipped_no_text)} 篇")


if __name__ == "__main__":
    main()
