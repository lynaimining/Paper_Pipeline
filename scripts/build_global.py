#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_global.py — 多机合并 + 全局 train/val/test 切分

支持多台机器各自跑 pipeline_final.py 后，把产出的 unified/ 目录合并成一个
全局数据集。跨机器的同 paper_id 记录保留 quality_score 最高的版本。

用法（单机）:
  python build_global.py \\
      --dataset-dirs /data/machine1 \\
      --output-dir   /data/global \\
      --split-ratio  0.8 0.1 0.1 --seed 42

用法（多机合并，127K 场景）:
  python build_global.py \\
      --dataset-dirs /data/machine1 /data/machine2 /data/machine3 \\
      --output-dir   /data/global \\
      --split-ratio  0.8 0.1 0.1 --seed 42

向后兼容旧参数（单机 --dataset-dir）:
  python build_global.py \\
      --dataset-dir  /data/machine1 \\
      --output-dir   /data/global
"""
import argparse
import json
import logging
import random
import sys
from collections import defaultdict
from pathlib import Path

_log = logging.getLogger(__name__)


# ── 分组键策略（决定切分粒度）────────────────────────────────────────────────
# 切分粒度从粗到细：
#   QA 条目级（❌ 最差）  — 同 paper 的不同问题分散在 train/test
#   paper 级（当前）      — 同矿区的不同论文可能分散（现阶段可接受）
#   矿区级（理想）        — 需要坐标聚类或 deposit_key 字段
#
# 升级路径：当 deepseek_extract 输出里有 deposit_key（矿区聚类 id）时，
# 把下面的函数改为 `return rec.get("deposit_key") or str(rec.get("paper_id"))`，
# 其余逻辑不变，即可升级到矿区级切分。

def _split_group_key(rec: dict) -> str:
    """
    当前使用 paper_id 级别；升级为矿区级时替换此函数。
    返回该 QA 记录的切分分组键，同一个键的所有记录落入同一个 split。
    """
    return str(rec.get("paper_id", "__unknown__"))


# ── 记录读取 ─────────────────────────────────────────────────────────────────

def _read_unified_dir(unified_dir: Path) -> tuple[list, int, int]:
    """
    读取单个 unified/ 目录下所有 .jsonl 文件。
    返回 (records, file_count, skip_count)。
    """
    records = []
    file_count = 0
    skip_count = 0
    for jf in sorted(unified_dir.glob("*.jsonl")):
        file_count += 1
        with open(jf, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    skip_count += 1
                    _log.warning(f"  WARN: {jf.name}:{lineno} JSON解析失败，跳过: {e}")
    return records, file_count, skip_count


def _dedup_by_quality(records: list) -> tuple[list, int]:
    """
    跨机器去重：同一 id 的 QA 条目保留 quality_score 最高版本。
    无 id 的记录按 (paper_id, question_hash) 兜底去重，防止无限注入。
    """
    import hashlib

    by_id: dict[str, dict] = {}
    # 无 id 记录：用 (paper_id + question前64字) 作为代理 key，防止重复注入
    by_proxy: dict[str, dict] = {}

    for rec in records:
        uid = rec.get("id")
        if uid:
            existing = by_id.get(uid)
            if existing is None or rec.get("quality_score", 0) > existing.get("quality_score", 0):
                by_id[uid] = rec
        else:
            # 用 paper_id + question 内容哈希作代理
            q = str(rec.get("paper_id", "")) + str(rec.get("conversations", ""))[:64]
            proxy = hashlib.md5(q.encode()).hexdigest()
            existing = by_proxy.get(proxy)
            if existing is None or rec.get("quality_score", 0) > existing.get("quality_score", 0):
                by_proxy[proxy] = rec

    deduped = list(by_id.values()) + list(by_proxy.values())
    dup_count = max(0, len(records) - len(deduped))
    return deduped, dup_count


# ── 主流程 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="多机合并 + 全局 train/val/test 切分",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # 新参数：支持多目录
    parser.add_argument(
        "--dataset-dirs", nargs="+", metavar="DIR",
        help="一个或多个 process_paper 输出根目录（各含 unified/ 子目录）",
    )
    # 旧参数：向后兼容单目录用法
    parser.add_argument(
        "--dataset-dir", metavar="DIR",
        help="（向后兼容）单个 dataset 目录，等价于 --dataset-dirs DIR",
    )
    parser.add_argument("--output-dir", required=True,
                        help="切分结果输出目录")
    parser.add_argument("--split-ratio", nargs=3, type=float, default=[0.8, 0.1, 0.1],
                        metavar=("TRAIN", "VAL", "TEST"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')

    # 合并 --dataset-dir 和 --dataset-dirs
    dirs = list(args.dataset_dirs or [])
    if args.dataset_dir:
        dirs.append(args.dataset_dir)
    if not dirs:
        parser.error("必须提供 --dataset-dirs 或 --dataset-dir")

    if abs(sum(args.split_ratio) - 1.0) > 1e-6:
        parser.error(f"--split-ratio 之和必须为 1.0，当前为 {sum(args.split_ratio):.6f}")

    output_dir = Path(args.output_dir)

    # ── 多目录收集 ────────────────────────────────────────────────────────────
    all_records = []
    total_files = 0
    total_skipped = 0

    for raw_dir in dirs:
        dataset_dir = Path(raw_dir)
        unified_dir = dataset_dir / "unified"
        if not unified_dir.exists():
            _log.error(f"ERROR: unified 目录不存在: {unified_dir}")
            sys.exit(1)
        recs, fc, sc = _read_unified_dir(unified_dir)
        all_records.extend(recs)
        total_files += fc
        total_skipped += sc
        _log.info(f"  读取 {unified_dir}: {len(recs)} 条 QA，来自 {fc} 个文件"
              + (f"，跳过 {sc} 坏行" if sc else ""))

    if not all_records:
        _log.error("ERROR: 没有读取到任何记录")
        sys.exit(1)

    raw_total = len(all_records)

    # ── 跨机器去重 ────────────────────────────────────────────────────────────
    all_records, dup_count = _dedup_by_quality(all_records)
    if dup_count:
        _log.info(f"  跨机器去重：移除 {dup_count} 条重复 QA（保留 quality_score 更高版本）")

    _log.info(f"\n合并后: {len(all_records)} 条 QA"
          + (f"（原始 {raw_total}，去重 {dup_count}）" if dup_count else "")
          + f"，来自 {len(dirs)} 个目录，{total_files} 个文件")

    # ── 分组 + 切分 ───────────────────────────────────────────────────────────
    group_map: dict[str, list] = defaultdict(list)
    for rec in all_records:
        group_map[_split_group_key(rec)].append(rec)

    group_keys = sorted(group_map.keys())
    rng = random.Random(args.seed)
    rng.shuffle(group_keys)

    n_groups = len(group_keys)
    train_r, val_r, _ = args.split_ratio
    n_train_g = int(n_groups * train_r)
    n_val_g   = int(n_groups * val_r)
    n_test_g  = n_groups - n_train_g - n_val_g

    if n_val_g == 0 or n_test_g == 0:
        _log.warning(f"  WARNING: 分组数({n_groups})太少，val={n_val_g} test={n_test_g}，"
              f"建议至少 {int(1/min(val_r, 1-train_r))+1} 个分组")

    train_keys = set(group_keys[:n_train_g])
    val_keys   = set(group_keys[n_train_g:n_train_g + n_val_g])
    test_keys  = set(group_keys[n_train_g + n_val_g:])

    def _flatten(keys_set: set) -> list:
        out = []
        for key in group_keys:
            if key in keys_set:
                out.extend(group_map[key])
        return out

    splits = {
        "train": _flatten(train_keys),
        "val":   _flatten(val_keys),
        "test":  _flatten(test_keys),
    }

    n_train = len(splits["train"])
    n_val   = len(splits["val"])
    n_test  = len(splits["test"])

    _log.info(f"切分粒度: paper 级（{n_groups} 个分组）")
    _log.info(f"  train: {n_train_g} 组 / {n_train} 条")
    _log.info(f"  val  : {n_val_g} 组 / {n_val} 条")
    _log.info(f"  test : {n_test_g} 组 / {n_test} 条")

    # ── 写出 ─────────────────────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    for split_name, records in splits.items():
        out_path = output_dir / f"{split_name}.jsonl"
        with open(out_path, "w", encoding="utf-8") as fh:
            for rec in records:
                rec["split"] = split_name
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _log.info(f"  → {out_path} ({len(records)} 条)")

    # ── unified_all.jsonl（全量合并，带 split 字段，供下游直接消费）─────────
    all_out = output_dir / "unified_all.jsonl"
    with open(all_out, "w", encoding="utf-8") as fh:
        for split_name, records in splits.items():
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    _log.info(f"  → {all_out} ({n_train + n_val + n_test} 条)")

    # ── splits.json（paper_id → split 映射，供 build_extractor_train / build_benchmark 使用）──
    import datetime
    splits_data = {
        "version": 1,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "seed": args.seed,
        "split_ratio": {"train": args.split_ratio[0], "val": args.split_ratio[1], "test": args.split_ratio[2]},
        "paper_counts": {"train": n_train_g, "val": n_val_g, "test": n_test_g},
        "paper_ids": {
            split_name: sorted(group_keys[
                {"train": slice(0, n_train_g),
                 "val":   slice(n_train_g, n_train_g + n_val_g),
                 "test":  slice(n_train_g + n_val_g, None)}[split_name]
            ])
            for split_name in ["train", "val", "test"]
        },
    }
    splits_path = output_dir / "splits.json"
    splits_path.write_text(json.dumps(splits_data, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info(f"  → {splits_path}")

    # ── stats.json（数据集统计，供分析和 dataset_card 使用）─────────────────
    # deposit_type/class 来自 index/*.json，而非 QA 记录（QA 记录不含这两个字段）
    dep_counter: dict = {}
    dep_class_counter: dict = {}
    for raw_dir in dirs:
        index_dir = Path(raw_dir) / "index"
        if index_dir.exists():
            for idx_file in index_dir.glob("*.json"):
                try:
                    idx = json.loads(idx_file.read_text(encoding="utf-8"))
                    dt = idx.get("deposit_type")
                    dc = idx.get("deposit_class")
                    if dt:
                        dep_counter[dt] = dep_counter.get(dt, 0) + 1
                    if dc:
                        dep_class_counter[dc] = dep_class_counter.get(dc, 0) + 1
                except Exception:
                    pass

    stats = {
        "n_papers_with_qa": n_groups,          # 有 QA 产出的论文数
        "n_papers_total": total_files,          # unified/ 下的文件总数（含0条QA的论文）
        "n_qa_total": n_train + n_val + n_test,
        "n_qa_train": n_train,
        "n_qa_val":   n_val,
        "n_qa_test":  n_test,
        "duplicates_removed": dup_count,
        "source_dirs": [str(Path(d).resolve()) for d in dirs],
        "seed": args.seed,
        "split_granularity": "paper",
        "deposit_type_distribution": dict(sorted(dep_counter.items(), key=lambda x: -x[1])),
        "deposit_class_distribution": dict(sorted(dep_class_counter.items(), key=lambda x: -x[1])),
    }
    stats_path = output_dir / "stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    _log.info(f"  → {stats_path}")

    # manifest（保留，供本管线追溯）
    manifest = {
        "seed": args.seed,
        "split_ratio": args.split_ratio,
        "split_granularity": "paper",
        "source_dirs": [str(Path(d).resolve()) for d in dirs],
        "total_qa": n_train + n_val + n_test,
        "train": n_train, "val": n_val, "test": n_test,
        "groups": n_groups,
        "duplicates_removed": dup_count,
    }
    (output_dir / "split_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _log.info(f"\n完成: {n_train + n_val + n_test} 条 QA，seed={args.seed}")


if __name__ == "__main__":
    main()
