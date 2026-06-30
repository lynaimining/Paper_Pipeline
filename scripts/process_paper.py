#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_paper.py — Pipeline v5: per-paper artifact -> ms-swift unified jsonl

用法:
  python process_paper.py --paper-id 2123
      --trusted-json config/trusted_100_papers.json
      --text-qa-jsonl /tmp/text_qa.jsonl
      --auto-dir "/path/to/corpus/1995/8/2123/auto"
      --image-qa-jsonl /tmp/image_qa_2123.jsonl
      --demoted-jsonl /tmp/demoted_2123.jsonl
      --output-dir dataset_final

契约: fail-hard。任一必需 artifact 缺失直接 raise + exit(1)，不 fail-soft。
"""
import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from collections import defaultdict

_log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a geology expert specializing in metallic mineral deposits, "
    "spatial ore genesis, and structural controls on mineralization. "
    "Answer questions about geological maps, cross-sections, and research papers accurately."
)


# ── 字段标准化 ────────────────────────────────────────────────────────────────

def normalize_coordinates(raw) -> dict | None:
    """各种坐标格式 → {"lat": float, "lon": float} 或 None���"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        lat = raw.get("lat") if raw.get("lat") is not None else raw.get("latitude")
        lon = raw.get("lon") if raw.get("lon") is not None else raw.get("longitude")
        if lat is not None and lon is not None:
            try:
                return {"lat": float(lat), "lon": float(lon)}
            except (ValueError, TypeError):
                return None
        return None
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            return {"lat": float(raw[0]), "lon": float(raw[1])}
        except (ValueError, TypeError):
            return None
    if isinstance(raw, str):
        raw = raw.strip()
        # 度分秒格式（秒可选）: "12°24'30"S, 131°12'45"E" 或 "12°24'S, 131°12'E"
        dms = re.findall(
            r"(\d+)°(\d+)'(?:(\d+(?:\.\d+)?)\")?([NS])\s*[,，]\s*(\d+)°(\d+)'(?:(\d+(?:\.\d+)?)\")?([EW])",
            raw
        )
        if dms:
            d = dms[0]
            lat = int(d[0]) + int(d[1]) / 60.0 + float(d[2] or 0) / 3600.0
            if d[3] == "S":
                lat = -lat
            lon = int(d[4]) + int(d[5]) / 60.0 + float(d[6] or 0) / 3600.0
            if d[7] == "W":
                lon = -lon
            return {"lat": round(lat, 6), "lon": round(lon, 6)}
        # 十进制格式: "-12.4, 131.2" 或 "-12.4 131.2"
        nums = re.findall(r"[-+]?\d+\.?\d*", raw)
        if len(nums) >= 2:
            try:
                lat, lon = float(nums[0]), float(nums[1])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return {"lat": lat, "lon": lon}
            except (ValueError, TypeError):
                pass
    return None


def normalize_commodities(raw) -> dict | None:
    """各种 commodities 格式 → {"primary": [...], "byproduct": [...], "trace": [...]} 或 None。"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        # 已经是新格式
        if any(k in raw for k in ("primary", "byproduct", "trace")):
            return {
                "primary":  [x for x in raw.get("primary", []) or [] if x],
                "byproduct": [x for x in raw.get("byproduct", []) or [] if x],
                "trace":    [x for x in raw.get("trace", []) or [] if x],
            }
        # 旧格式 dict，值是列表（例如 {"Au": ["Au"], "Ag": ["Ag"]}）
        flat = []
        for v in raw.values():
            if isinstance(v, list):
                flat.extend(x for x in v if x)
            elif isinstance(v, str) and v:
                flat.append(v)
        return {"primary": flat, "byproduct": [], "trace": []} if flat else None
    if isinstance(raw, list):
        items = [x for x in raw if x]
        return {"primary": items, "byproduct": [], "trace": []} if items else None
    if isinstance(raw, str) and raw.strip():
        return {"primary": [raw.strip()], "byproduct": [], "trace": []}
    return None


def normalize_struct(record: dict) -> dict:
    """对 trusted record 做字段标准化，返回副本，不修改原始对象。"""
    r = dict(record)
    r["coordinates"] = normalize_coordinates(r.get("coordinates"))
    r["commodities"] = normalize_commodities(r.get("commodities"))
    return r


# ── 论文全文 markdown 保存 ────────────────────────────────────────────────────

def _safe_filename(paper_id: str) -> str:
    """把 paper_id 转成安全文件名：去除路径分隔符和控制字符，限制长度。"""
    safe = re.sub(r'[/\\:\*\?"<>|\r\n\t]', '_', str(paper_id))
    return safe[:200]  # 文件系统路径名上限通常 255 字节


def save_paper_text(paper_id: str, auto_dir: Path, text_dir: Path) -> str | None:
    """
    从 auto_dir 找论文主 .md 文件，复制到 text_dir/<paper_id>.md。
    返回目标路径字符串，找不到则返回 None。
    排除 MinerU 的中间产物（_layout, _middle, _model, _spans, _content_list）。
    """
    if auto_dir is None or not auto_dir.exists():
        return None

    exclude = ("_layout", "_middle", "_model", "_spans", "_content_list")
    candidates = [
        p for p in auto_dir.glob("*.md")
        if not any(x in p.name for x in exclude)
    ]
    if not candidates:
        return None

    # 优先选文件名含 paper_id 的，其次选最大的（最可能是全文）
    main_md = next((p for p in candidates if paper_id in p.name), None)
    if main_md is None:
        main_md = max(candidates, key=lambda p: p.stat().st_size)

    text_dir.mkdir(parents=True, exist_ok=True)
    dest = text_dir / f"{paper_id}.md"
    if not dest.exists():
        shutil.copy2(main_md, dest)
    return str(dest)


def quality_score(record: dict) -> float:
    """统一 quality_score 公式，输出 [0, 1]。"""
    has_gt = 1.0 if record.get("has_ground_truth") else 0.0
    conf_raw = record.get("confidence", None)
    if conf_raw is None:
        conf = 0.5
    elif isinstance(conf_raw, (int, float)):
        conf = float(conf_raw)
    else:
        conf = 0.5
    # tier 字段可能是 _gate_status (pass/warn/fail) 或旧式 gold/silver
    tier = record.get("tier", "")
    _tier_map = {"pass": 1.0, "warn": 0.5, "fail": 0.0, "gold": 1.0, "silver": 0.5}
    tier_score = _tier_map.get(tier, 0.0)
    n_refs = min(record.get("n_body_refs", 0) / 3.0, 1.0)
    return round(0.4 * has_gt + 0.3 * conf + 0.1 * tier_score + 0.2 * n_refs, 4)


def wrap_text_qa(record: dict, paper_id: str, trusted_record: dict | None = None) -> dict:
    """文本 QA -> LLaMA-Factory ShareGPT 格式。trusted_record 用于计算真实 quality_score。"""
    tr = trusted_record or {}
    qs = quality_score({
        "has_ground_truth": True,
        "confidence": tr.get("deposit_type_conf") if tr.get("deposit_type_conf") is not None else 0.5,
        "tier": tr.get("_gate_status", ""),
        "n_body_refs": 0,  # 所有批次统一为0，保证跨批次分数可比
    })
    return {
        "id": record["id"],
        "paper_id": paper_id,
        "qa_type": "text",
        "source": record.get("source", "template"),
        "dimension": record.get("dimension", ""),
        "quality_score": qs,
        "split": "",
        "conversations": [
            {"from": "system", "value": SYSTEM_PROMPT},
            {"from": "human", "value": record["question"]},
            {"from": "gpt", "value": record["answer"]},
        ],
    }


def wrap_image_qa_group(image_rel_path: str, qa_records: list, paper_id: str,
                        trusted_record: dict | None = None) -> dict:
    """
    同一张图的多条 QA 聚合为多轮对话（LLaMA-Factory ShareGPT 多模态格式）。
    图像路径放在顶层 images 列表；第一个 human turn 嵌入 <image> token。
    """
    if not qa_records:
        raise ValueError(f"wrap_image_qa_group: qa_records 不能为空 (image={image_rel_path})")
    first = qa_records[0]

    conversations = [{"from": "system", "value": SYSTEM_PROMPT}]
    for i, qa in enumerate(qa_records):
        if i == 0:
            # <image> token 放在问题文本前，与 images 列表的顺序对应
            conversations.append({
                "from": "human",
                "value": f"<image>\n{qa['question']}",
            })
        else:
            conversations.append({"from": "human", "value": qa["question"]})
        conversations.append({"from": "gpt", "value": qa["answer"]})

    # 用论文级别的 gate_status 作为 tier，而不是图 QA 记录自身（后者从不含 tier 字段）
    paper_tier = (trusted_record or {}).get("_gate_status", "")
    group_score = max(
        quality_score({
            "has_ground_truth": r.get("has_ground_truth", False),
            "confidence": r.get("confidence"),
            "tier": paper_tier,
            "n_body_refs": r.get("n_body_refs", 0),
        })
        for r in qa_records
    )

    uid_raw = f"{paper_id}::img::{image_rel_path}"
    uid = hashlib.md5(uid_raw.encode()).hexdigest()[:12]

    return {
        "id": f"imggrp_{uid}",
        "paper_id": paper_id,
        "qa_type": "image",
        "source": first.get("generation_method", "ground_truth_driven"),
        "dimension": "visual_spatial",
        "figure_category": first.get("category", ""),
        "quality_score": group_score,
        "split": "",
        "images": [image_rel_path],
        "conversations": conversations,
    }


def rewrite_image_path(abs_path: str, paper_id: str, images_dir: Path) -> tuple[str, Path]:
    """
    绝对路径 -> 相对路径 images/<paper_id>/<hash>.jpg。
    同时在 dataset/images/ 下建 symlink 指回原始文件。
    安全：验证 symlink 目标在 images_dir 内，防止路径穿越。
    返回 (rel_path, symlink_target_path)。
    """
    src = Path(abs_path)
    safe_pid = _safe_filename(paper_id)
    dest_dir = images_dir / safe_pid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    rel = f"images/{safe_pid}/{src.name}"
    if not dest.exists() and not dest.is_symlink():
        # 安全检查：确保 dest 在 images_dir 内（防止 paper_id 路径穿越）
        try:
            dest.relative_to(images_dir.resolve())
        except ValueError:
            raise ValueError(f"路径穿越攻击拒绝: {dest} 不在 {images_dir} 内")
        os.symlink(src.resolve(), dest)
    return rel, dest


def load_jsonl(path) -> list:
    if path is None or not Path(path).exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                _log.warning(f"  WARN: {path}:{lineno} JSON 解析失败，跳过该行: {e}")
    return records


def process_paper(
    paper_id: str,
    trusted_record: dict,
    text_qa_all: list,
    output_dir: Path,
    auto_dir: Path | None = None,
    image_qa_jsonl: str | None = None,
    demoted_jsonl: str | None = None,
) -> dict:
    """
    处理单篇 paper，输出到 output_dir/unified/<paper_id>.jsonl。
    返回 index 元数据 dict。
    """
    unified_dir = output_dir / "unified"
    images_dir = output_dir / "images"
    struct_dir = output_dir / "struct"
    index_dir = output_dir / "index"
    logs_dir = output_dir / "_logs"
    for d in [unified_dir, images_dir, struct_dir, index_dir, logs_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 对 paper_id 做文件名安全化，防止含 '/' 等字符创建子目录或路径穿越
    safe_pid = _safe_filename(paper_id)

    out_path = unified_dir / f"{safe_pid}.jsonl"
    log_path = logs_dir / f"{safe_pid}.log"
    records = []
    log_lines = []

    # ── 文本 QA ─────────────────────────────────────────────────────────────
    text_qa = [r for r in text_qa_all if str(r.get("paper_id")) == str(paper_id)]
    for r in text_qa:
        records.append(wrap_text_qa(r, paper_id, trusted_record))
    log_lines.append(f"text_qa: {len(text_qa)} records")

    # ── 图 QA ────────────────────────────────────────────────────────────────
    image_qa_raw = load_jsonl(image_qa_jsonl)
    paper_image_qa = [r for r in image_qa_raw if str(r.get("paper_id")) == str(paper_id)]

    # 按图路径分组（多 QA 同图 → 多轮）
    by_image = defaultdict(list)
    for r in paper_image_qa:
        abs_img = r.get("image", "")
        by_image[abs_img].append(r)

    img_group_count = 0
    for abs_img, group in by_image.items():
        if not abs_img:
            continue
        rel_path, _ = rewrite_image_path(abs_img, paper_id, images_dir)
        records.append(wrap_image_qa_group(rel_path, group, paper_id,
                                             trusted_record=trusted_record))
        img_group_count += 1
    log_lines.append(f"image_qa_groups: {img_group_count} (raw: {len(paper_image_qa)})")

    # ── blind-test demoted（并入文本流）─────────────────────────────────────
    demoted_raw = load_jsonl(demoted_jsonl)
    paper_demoted = [r for r in demoted_raw if str(r.get("paper_id")) == str(paper_id)]
    for r in paper_demoted:
        entry = wrap_text_qa(r, paper_id, trusted_record)
        entry["source"] = "text_from_image"
        records.append(entry)
    log_lines.append(f"demoted_qa: {len(paper_demoted)} records")

    # ── 标准化 trusted_record 后写 struct ────────────────────────────────────
    struct_path = struct_dir / f"{safe_pid}.json"
    normalized = normalize_struct(trusted_record)
    struct_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2))

    # ── 保存论文全文 markdown ─────────────────────────────────────────────────
    text_dir = output_dir / "text"
    text_path = save_paper_text(paper_id, auto_dir, text_dir)
    log_lines.append(f"text_saved: {text_path or 'not found'}")

    # ── 写 unified jsonl ──────────────────────────────────────────────────────
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ── 写 index ──────────────────────────────────────────────────────────────
    index = {
        "paper_id": paper_id,
        "deposit_type": normalized.get("deposit_type"),
        "deposit_class": normalized.get("deposit_class"),
        "coordinates": normalized.get("coordinates"),
        "n_text_qa": len(text_qa) + len(paper_demoted),
        "n_image_groups": img_group_count,
        "n_total": len(records),
        "unified_path": str(out_path),
        "struct_path": str(struct_path),
        "text_path": text_path,
        "auto_dir": str(auto_dir) if auto_dir else None,
    }
    (index_dir / f"{safe_pid}.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))
    log_path.write_text("\n".join(log_lines) + "\n")
    return index


def main():
    parser = argparse.ArgumentParser(description="Pipeline Final: per-paper -> unified ShareGPT jsonl")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--trusted-json", required=True, help="全量 trusted.json")
    parser.add_argument("--text-qa-jsonl", required=True, help="generate_qa.py 输出的全量 JSONL")
    parser.add_argument("--auto-dir", default=None, help="MinerU auto/ 目录（可选）")
    parser.add_argument("--image-qa-jsonl", default=None, help="optimized_qa_pipeline 图 QA 输出（可选）")
    parser.add_argument("--demoted-jsonl", default=None, help="blind-test 降级 QA（可选）")
    parser.add_argument("--output-dir", default="dataset", help="输出根目录")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')

    trusted_all = json.loads(Path(args.trusted_json).read_text())
    trusted_map = {str(r["paper_id"]).strip(): r for r in trusted_all}  # strip 防止末尾空格导致 lookup 失败

    if args.paper_id not in trusted_map:
        _log.error(f"ERROR: paper_id '{args.paper_id}' not found in {args.trusted_json}")
        sys.exit(1)

    text_qa_all = load_jsonl(args.text_qa_jsonl)
    if not text_qa_all:
        _log.error(f"ERROR: text_qa_jsonl '{args.text_qa_jsonl}' is empty or missing")
        sys.exit(1)

    auto_dir = Path(args.auto_dir) if args.auto_dir else None
    if auto_dir and not auto_dir.exists():
        _log.error(f"ERROR: auto_dir '{auto_dir}' does not exist")
        sys.exit(1)

    index = process_paper(
        paper_id=args.paper_id,
        trusted_record=trusted_map[args.paper_id],
        text_qa_all=text_qa_all,
        output_dir=Path(args.output_dir),
        auto_dir=auto_dir,
        image_qa_jsonl=args.image_qa_jsonl,
        demoted_jsonl=args.demoted_jsonl,
    )
    _log.info(json.dumps(index, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
