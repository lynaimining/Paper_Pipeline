#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_global.py — Pipeline v5: 全局聚合 + paper 级别 train/val/test 切分

用法:
  python build_global.py --dataset-dir dataset --output-dir dataset
  python build_global.py --dataset-dir dataset --split-ratio 0.8 0.1 0.1 --seed 42
"""
import argparse
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Pipeline v5: 全局聚合 + 切分")
    parser.add_argument("--dataset-dir", default="dataset", help="process_paper.py 的 output-dir")
    parser.add_argument("--output-dir", default=None, help="输出目录（默认同 dataset-dir）")
    parser.add_argument("--split-ratio", nargs=3, type=float, default=[0.8, 0.1, 0.1],
                        metavar=("TRAIN", "VAL", "TEST"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    ds_dir = Path(args.dataset_dir)
    out_dir = Path(args.output_dir) if args.output_dir else ds_dir

    # ── 收集所有 index ────────────────────────────────────────────────────
    index_dir = ds_dir / "index"
    if not index_dir.exists():
        raise FileNotFoundError(f"index 目录不存在: {index_dir}，请先跑 pipeline_final.py")

    indices = []
    for f in sorted(index_dir.glob("*.json")):
        indices.append(json.loads(f.read_text()))

    if not indices:
        raise ValueError("没有找到任何 index 文件，请先跑 pipeline_final.py")

    paper_ids = [idx["paper_id"] for idx in indices]
    print(f"找到 {len(paper_ids)} 篇论文的 unified jsonl")

    # ── paper 级别 train/val/test 切分 ────────────────────────────────────
    rng = random.Random(args.seed)
    shuffled = list(paper_ids)
    rng.shuffle(shuffled)

    train_r, val_r, test_r = args.split_ratio
    total = len(shuffled)
    n_train = max(1, round(total * train_r))
    n_val = max(1, round(total * val_r))
    n_test = total - n_train - n_val
    if n_test < 0:
        n_val += n_test
        n_test = 0

    split_map = {}
    for pid in shuffled[:n_train]:
        split_map[pid] = "train"
    for pid in shuffled[n_train:n_train + n_val]:
        split_map[pid] = "val"
    for pid in shuffled[n_train + n_val:]:
        split_map[pid] = "test"

    print(f"切分 (seed={args.seed}): train={n_train} val={n_val} test={n_test}")

    # ── 读入所有 unified jsonl，回填 split 字段 ───────────────────────────
    all_records = []
    unified_dir = ds_dir / "unified"
    missing = []
    for idx in indices:
        pid = idx["paper_id"]
        u_path = Path(idx.get("unified_path", str(unified_dir / f"{pid}.jsonl")))
        if not u_path.exists():
            missing.append(pid)
            continue
        split = split_map.get(pid, "train")
        with open(u_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rec["split"] = split
                all_records.append(rec)

    if missing:
        print(f"WARNING: {len(missing)} 篇 unified jsonl 缺失，已跳过: {missing}")

    # ── 按 split 输出 ────────────────────────────────────────────────────
    by_split = defaultdict(list)
    for rec in all_records:
        by_split[rec["split"]].append(rec)

    out_dir.mkdir(parents=True, exist_ok=True)

    # 写 unified_all.jsonl（全量，含 split 字段）
    all_path = out_dir / "unified_all.jsonl"
    with open(all_path, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"全量: {all_path} ({len(all_records)} 条)")

    # 写各 split 文件
    for split_name in ["train", "val", "test"]:
        recs = by_split[split_name]
        if not recs:
            continue
        sp_path = out_dir / f"{split_name}.jsonl"
        with open(sp_path, "w", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  {split_name}: {sp_path} ({len(recs)} 条)")

    # ── splits.json（paper_id → split 映射）──────────────────────────────
    splits_path = out_dir / "splits.json"
    splits_data = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "split_ratio": {"train": train_r, "val": val_r, "test": test_r},
        "paper_counts": {"train": n_train, "val": n_val, "test": n_test},
        "paper_ids": {
            "train": [p for p, s in split_map.items() if s == "train"],
            "val":   [p for p, s in split_map.items() if s == "val"],
            "test":  [p for p, s in split_map.items() if s == "test"],
        },
        "split_map": split_map,
    }
    splits_path.write_text(json.dumps(splits_data, ensure_ascii=False, indent=2))

    # ── stats.json ────────────────────────────────────────────────────────
    dep_counter = Counter(idx.get("deposit_type") or "unknown" for idx in indices)
    qa_type_counter = Counter(rec.get("qa_type", "text") for rec in all_records)
    split_counter = Counter(rec.get("split", "") for rec in all_records)

    stats = {
        "n_papers": len(paper_ids),
        "n_qa_total": len(all_records),
        "split_qa_counts": dict(split_counter),
        "split_paper_counts": {"train": n_train, "val": n_val, "test": n_test},
        "qa_type_distribution": dict(qa_type_counter),
        "deposit_type_distribution": dict(dep_counter.most_common()),
    }
    stats_path = out_dir / "stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2))

    # ── dataset_card.md ──────────────────────────────────────────────────
    card_lines = [
        "# Paper Pipeline Final — Dataset Card",
        "",
        f"**Papers**: {stats['n_papers']}  ",
        f"**QA total**: {stats['n_qa_total']}  ",
        f"**Split (paper-level)**: train={n_train} / val={n_val} / test={n_test}  ",
        "",
        "## QA Type",
        *[f"- {k}: {v}" for k, v in sorted(qa_type_counter.items())],
        "",
        "## Deposit Type Distribution",
        *[f"- {k}: {v}" for k, v in dep_counter.most_common()],
        "",
        "## Files",
        "- `unified_all.jsonl` — full dataset (ShareGPT format) with split field",
        "- `train.jsonl` / `val.jsonl` / `test.jsonl` — pre-split files for LLaMA-Factory",
        "- `splits.json` — paper_id → split mapping",
        "- `stats.json` — dataset statistics",
        "",
        "## ShareGPT Format",
        "Each entry uses `conversations` (from/value pairs) per LLaMA-Factory convention.",
        "Visual entries have a top-level `images` list; `<image>` token is embedded in the first human turn.",
    ]
    card_path = out_dir / "dataset_card.md"
    card_path.write_text("\n".join(card_lines))

    print(f"\nstats   → {stats_path}")
    print(f"card    → {card_path}")
    print(f"splits  → {splits_path}")
    print("Done.")


if __name__ == "__main__":
    main()
