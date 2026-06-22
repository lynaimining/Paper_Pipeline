#!/usr/bin/env python3
"""
Pipeline v4 后处理：清洗 → 矿床坐标匹配 → 成矿带推断 → 质量报告
用法: python postprocess.py <input.json> <output.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from clean_geochemistry import clean_batch
from build_global_db import DepositMatcher, load_manual_global_deposits
from match_belt_coordinates import BELT_COORDINATES
from expand_belt_db import MANUAL_BELT_ADDITIONS


def _normalize(s):
    return s.replace('–', '-').replace('—', '-').replace('‒', '-').lower()


def run_postprocess(input_json: str, output_json: str, verbose: bool = True) -> dict:
    """
    完整后处理流水线：
    Step 1: 清洗 geochemistry 空结构
    Step 2: 全球矿床数据库坐标匹配（USGS MRDS + 手工库）
    Step 3: 成矿带坐标推断（225条成矿带库）
    Step 4: 保存结果
    """
    with open(input_json) as f:
        data = json.load(f)

    total = len(data)
    if verbose:
        print(f"后处理: {total} 篇")

    # Step 1: 清洗 geochemistry 空结构
    cleaned = clean_batch(data)
    if verbose:
        print(f"  Step1 清洗空结构: {cleaned}篇")

    # Step 2: 全球矿床数据库匹配
    mrds_path = Path(__file__).parent / "mrds_deposits.json"
    manual_global = load_manual_global_deposits()
    matcher = DepositMatcher(str(mrds_path), manual_global)
    stats = matcher.batch_match(data)
    if verbose:
        print(f"  Step2 矿床库匹配: +{stats['matched']}篇坐标")

    # Step 3: 成矿带推断 + _provenance 溯源标注（P3）
    all_belts = dict(BELT_COORDINATES)
    all_belts.update(MANUAL_BELT_ADDITIONS)

    belt_added = 0
    for r in data:
        rec = r.get("extracted") or r

        # 记录本次坐标匹配前的来源（Step2 中 mrds_match 已写入 coordinates）
        coord_source_before = "llm_extracted"
        if rec.get("coordinates"):
            src = (rec["coordinates"] or {}).get("extraction_method", "")
            if "mrds" in src.lower() or "database" in src.lower() or "db" in src.lower():
                coord_source_before = "mrds_match"
            elif "成矿带" in src or "belt" in src.lower():
                coord_source_before = "belt_inferred"

        if not rec.get("coordinates"):
            text = _normalize(
                f"{rec.get('metallogenic_belt') or ''} {rec.get('tectonic_setting') or ''}"
            )
            for known, coords in all_belts.items():
                if _normalize(known) in text:
                    rec["coordinates"] = {
                        "latitude": coords[0],
                        "longitude": coords[1],
                        "precision": "成矿带级",
                        "source": f"成矿带库-{known}",
                        "confidence": 0.55,
                        "extraction_method": "成矿带推断"
                    }
                    belt_added += 1
                    break

        # 确定最终坐标来源
        if rec.get("coordinates"):
            src = (rec["coordinates"] or {}).get("extraction_method", "")
            if "成矿带" in src or "belt" in src.lower():
                coord_src = "belt_inferred"
            elif "mrds" in src.lower() or "database" in src.lower():
                coord_src = "mrds_match"
            else:
                coord_src = "llm_extracted"
        else:
            coord_src = "none"

        # 置信度分级
        conf = rec.get("deposit_type_conf") or 0
        has_coords = bool(rec.get("coordinates"))
        coord_conf = (rec.get("coordinates") or {}).get("confidence", 0) if has_coords else 0
        if conf >= 0.8 and coord_src == "llm_extracted" and coord_conf >= 0.8:
            confidence_tier = "high"
        elif conf >= 0.6 or (has_coords and coord_conf >= 0.6):
            confidence_tier = "medium"
        else:
            confidence_tier = "low"

        # 写入 _provenance（F2 血缘标注）
        rec["_provenance"] = {
            "coordinates_source": coord_src,
            "deposit_type_verified": False,  # P2 对抗复核通过后设为 True
            "extraction_pipeline": "v4.1.0",
            "confidence_tier": confidence_tier,
        }

    if verbose:
        print(f"  Step3 成矿带推断: +{belt_added}篇坐标")

    # 最终统计
    with_coords = sum(1 for r in data if (r.get("extracted") or r).get("coordinates"))
    if verbose:
        print(f"  坐标覆盖: {with_coords}/{total} ({with_coords/total*100:.1f}%)")

    # 保存
    with open(output_json, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"  输出: {output_json}")

    return {
        "total": total,
        "cleaned_geochem": cleaned,
        "coords_from_db": stats["matched"],
        "coords_from_belt": belt_added,
        "coords_total": with_coords,
        "coords_rate": with_coords / total,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python postprocess.py <input.json> <output.json>")
        sys.exit(1)
    run_postprocess(sys.argv[1], sys.argv[2])
