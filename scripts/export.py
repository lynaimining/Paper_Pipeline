#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export.py — 从 _source/ 生成下游消费层

支持的目标：
  A  A_vlm_sft/       LLaMA-Factory ShareGPT 训练集（train/val/test.jsonl）
  B  B_structured_db/ 结构化矿床数据库（deposits.jsonl + deposits.csv）

用法:
  python export.py --source-dir dataset/_source --output-dir dataset --targets A B
  python export.py --source-dir dataset/_source --output-dir dataset --targets A
"""
import argparse
import csv
import json
import shutil
from pathlib import Path


# ── A: VLM SFT ────────────────────────────────────────────────────────────────

def export_A(source_dir: Path, output_dir: Path, copy_images: bool = False) -> None:
    """
    从 build_global.py 已产出的 train/val/test.jsonl 直接复制到 A_vlm_sft/，
    避免重复解析 unified/*.jsonl。
    """
    out_dir = output_dir / "A_vlm_sft"
    out_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for split_name in ["train", "val", "test"]:
        src_path = source_dir / f"{split_name}.jsonl"
        if not src_path.exists():
            continue
        dst_path = out_dir / f"{split_name}.jsonl"
        shutil.copy2(src_path, dst_path)
        with open(dst_path, encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
        print(f"  A/{split_name}.jsonl  {n} 条")
        total += n

    # dataset_info.json（LLaMA-Factory 注册）
    dataset_info = {
        "geology_mineral_train": {
            "file_name": "train.jsonl",
            "formatting": "sharegpt",
            "columns": {"conversations": "conversations", "images": "images"},
        },
        "geology_mineral_val": {
            "file_name": "val.jsonl",
            "formatting": "sharegpt",
            "columns": {"conversations": "conversations", "images": "images"},
        },
        "geology_mineral_test": {
            "file_name": "test.jsonl",
            "formatting": "sharegpt",
            "columns": {"conversations": "conversations", "images": "images"},
        },
    }
    (out_dir / "dataset_info.json").write_text(
        json.dumps(dataset_info, ensure_ascii=False, indent=2)
    )

    # images/ 处理
    src_images = source_dir / "images"
    dst_images = out_dir / "images"
    if src_images.exists():
        if copy_images:
            if dst_images.exists():
                shutil.rmtree(dst_images)
            shutil.copytree(src_images, dst_images)
            print(f"  A/images/ 已复制（实体文件）")
        else:
            if not dst_images.exists():
                dst_images.symlink_to(src_images.resolve())
            print(f"  A/images/ → symlink to {src_images.resolve()}")

    print(f"  A 完成: {total} 条 QA → {out_dir}")


# ── B: Structured DB ──────────────────────────────────────────────────────────

# 平铺字段顺序（CSV 列顺序）
_B_FIELDS = [
    "paper_id", "deposit_type", "deposit_class",
    "lat", "lon",
    "age_min_ma", "age_max_ma",
    "commodities_primary", "commodities_byproduct",
    "metallogenic_belt", "tectonic_setting", "country",
    "host_rocks", "alteration", "structural_controls",
    "deposit_scale_class", "confidence", "has_ground_truth",
    "source_year", "pipeline_version",
]


def _flatten_struct(record: dict) -> dict:
    """将 struct/<paper_id>.json 里的嵌套字段平铺为数据库行。"""
    coords = record.get("coordinates") or {}
    ages = record.get("ages") or []
    comms = record.get("commodities") or {}
    scale = record.get("deposit_scale") or {}

    age_values = []
    for a in (ages if isinstance(ages, list) else []):
        v = a.get("age_ma") if isinstance(a, dict) else None
        if v is not None:
            try:
                age_values.append(float(v))
            except (ValueError, TypeError):
                pass

    if isinstance(comms, list):
        comm_primary = ", ".join(str(x) for x in comms)
        comm_byproduct = ""
    elif isinstance(comms, dict):
        comm_primary   = ", ".join(str(x) for x in (comms.get("primary") or []))
        comm_byproduct = ", ".join(str(x) for x in (comms.get("byproduct") or []))
    else:
        comm_primary = comm_byproduct = ""

    def _join(v):
        if isinstance(v, list):
            return "; ".join(str(x) for x in v if x is not None)
        return str(v) if v is not None else ""

    def _sanitize_csv(val: str) -> str:
        """防 Excel formula injection（OWASP CSV Injection）：以 =/@/+/- 开头时加单引号前缀。"""
        if val and val[0] in ('=', '@', '+', '-', '\t', '\r'):
            return "'" + val
        return val

    return {
        "paper_id":            str(record.get("paper_id", "")),
        "deposit_type":        record.get("deposit_type") or "",
        "deposit_class":       record.get("deposit_class") or "",
        "lat":                 coords.get("lat") if isinstance(coords, dict) else None,
        "lon":                 coords.get("lon") if isinstance(coords, dict) else None,
        "age_min_ma":          min(age_values) if age_values else None,
        "age_max_ma":          max(age_values) if age_values else None,
        "commodities_primary":   comm_primary,
        "commodities_byproduct": comm_byproduct,
        "metallogenic_belt":   _sanitize_csv(record.get("metallogenic_belt") or ""),
        "tectonic_setting":    _sanitize_csv(record.get("tectonic_setting") or ""),
        "country":             _sanitize_csv(_join(record.get("countries") or record.get("country") or [])),
        "host_rocks":          _sanitize_csv(_join(record.get("host_rocks"))),
        "alteration":          _sanitize_csv(_join(record.get("alteration"))),
        "structural_controls": _sanitize_csv(_join(record.get("structural_controls"))),
        "deposit_scale_class": scale.get("scale_class") if isinstance(scale, dict) else "",
        "confidence":          record.get("confidence"),
        "has_ground_truth":    record.get("has_ground_truth"),
        "source_year":         record.get("source_year") or "",
        "pipeline_version":    record.get("pipeline_version") or "final-v1",
    }


def export_B(source_dir: Path, output_dir: Path) -> None:
    struct_dir = source_dir / "struct"
    if not struct_dir.exists():
        raise FileNotFoundError(f"struct/ 目录不存在: {struct_dir}")

    out_dir = output_dir / "B_structured_db"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for struct_file in sorted(struct_dir.glob("*.json")):
        try:
            record = json.loads(struct_file.read_text(encoding="utf-8"))
            rows.append(_flatten_struct(record))
        except Exception as e:
            print(f"  [WARN] {struct_file.name}: {e}")

    # deposits.jsonl
    jsonl_path = out_dir / "deposits.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # deposits.csv — None 值替换为空字符串，避免 pandas read_csv 报 "None" 转 float 失败
    csv_path = out_dir / "deposits.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_B_FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            csv_row = {k: ("" if v is None else v) for k, v in row.items()}
            writer.writerow(csv_row)

    # georeferenced 子集（有坐标的记录）
    geo_rows = [r for r in rows if r.get("lat") is not None and r.get("lon") is not None]
    geo_path = out_dir / "deposits_georeferenced.jsonl"
    with open(geo_path, "w", encoding="utf-8") as f:
        for row in geo_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # deposits_georeferenced.geojson
    geojson_path = out_dir / "deposits_georeferenced.geojson"
    features = []
    for row in geo_rows:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row["lon"], row["lat"]],  # GeoJSON: [lon, lat]
            },
            "properties": {k: v for k, v in row.items() if k not in ("lat", "lon")},
        })
    geojson = {"type": "FeatureCollection", "features": features}
    geojson_path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  B 完成: {len(rows)} 条（{len(geo_rows)} 条含坐标）→ {out_dir}")
    print(f"    deposits.jsonl / deposits.csv / deposits_georeferenced.jsonl / deposits_georeferenced.geojson")


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="从 _source/ 导出下游消费层")
    parser.add_argument("--source-dir", required=True, help="_source/ 目录路径")
    parser.add_argument("--output-dir", required=True, help="输出根目录（A_vlm_sft/ 等建在这里）")
    parser.add_argument("--targets", nargs="+", choices=["A", "B", "C", "D", "E"], default=["A", "B"],
                        help="要生成的目标（默认全部）")
    parser.add_argument("--copy-images", action="store_true",
                        help="A 层：实体复制图像（用于跨机部署）；默认只建 symlink")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)

    if not source_dir.exists():
        print(f"ERROR: source_dir 不存在: {source_dir}")
        raise SystemExit(1)

    if "A" in args.targets:
        print("\n[Export A] VLM SFT 训练集")
        export_A(source_dir, output_dir, copy_images=args.copy_images)

    if "B" in args.targets:
        print("\n[Export B] 结构化矿床数据库")
        export_B(source_dir, output_dir)

    if "C" in args.targets:
        print("\n[Export C] 抽取器训练数据")
        import subprocess, sys
        subprocess.run([
            sys.executable,
            str(Path(__file__).parent / "build_extractor_train.py"),
            "--source-dir", str(source_dir),
            "--output-dir", str(output_dir),
        ], check=True)

    if "D" in args.targets:
        print("\n[Export D] Benchmark 评测集")
        import subprocess, sys
        subprocess.run([
            sys.executable,
            str(Path(__file__).parent / "build_benchmark.py"),
            "--source-dir", str(source_dir),
            "--output-dir", str(output_dir),
        ], check=True)

    if "E" in args.targets:
        print("\n[Export E] DAPT 预训练语料")
        import subprocess, sys
        subprocess.run([
            sys.executable,
            str(Path(__file__).parent / "build_corpus.py"),
            "--source-dir", str(source_dir),
            "--output-dir", str(output_dir),
        ], check=True)

    print("\n导出完成。")


if __name__ == "__main__":
    main()
