#!/usr/bin/env python3
"""
Pipeline v4 半自动评测框架 (P0)
──────────────────────────────
策略：
  1. 从 pilot 结果中按 deposit_type + reference_deposits 匹配 famous_deposits 数据库
  2. 西藏/Tibet/Gangdese/Sanjiang 斑岩铜矿论文单独输出 check 清单，供用户人工确认
  3. 对已知矿床（参考矿床名 in famous_deposits）计算自动验证得分
  4. 输出 eval_report.json + 人工 check 清单 TIBET_PORPHYRY_CHECK.md

用法:
  python eval.py <pilot_results.json> [--out-dir <dir>]
"""
import sys, json, re, argparse
from pathlib import Path
from collections import defaultdict

# ── 受控词表族群映射（同族得 0.5 分，完全匹配得 1.0 分）──
FAMILY_MAP = {
    "PORPHYRY":    {"PORPHYRY", "PORPHYRY-SKARN", "PORPHYRY-CU", "PORPHYRY-CU-AU", "PORPHYRY-CU-MO",
                    "PORPHYRY-MO", "PORPHYRY-AU", "PORPHYRY-SN", "PORPHYRY-W",
                    "PORPHYRY-AU-CU", "PORPHYRY-SKARN"},
    "EPITHERMAL":  {"EPITHERMAL", "EPITHERMAL-HS", "EPITHERMAL-IS", "EPITHERMAL-LS",
                    "EPITHERMAL-AU", "EPITHERMAL-AG", "EPITHERMAL-AG-AU", "ALUNITE-AU"},
    "OROG-AU":     {"OROG-AU"},
    "PLACER-AU":   {"PLACER-AU", "PLACER-AU-PALEO", "OROG-AU-PALEO"},
    "SKARN":       {"SKARN", "SKARN-CU-AU", "SKARN-CU", "SKARN-PB-ZN", "SKARN-FE",
                    "SKARN-W", "SKARN-W-SN", "SKARN-SN", "SKARN-AU", "SKARN-MN",
                    "SKARN-CU-FE"},
    "VMS":         {"VMS", "SMS"},
    "SEDEX":       {"SEDEX"},
    "MVT":         {"MVT", "IRISH-PB-ZN"},
    "IOCG":        {"IOCG", "KIRUNA-FE"},
    "NI-CU":       {"NI-CU", "NI-CU-PGE"},
    "PGE":         {"PGE-REEF", "PGE-CR", "CR-OPHIOLITE", "CR-STRATIFORM", "PLACER-PGE"},
    "CARBONATITE": {"CARBONATITE", "CARBONATITE-REE", "CARBONATITE-NB", "CARBONATITE-P",
                    "CARBONATITE-SKARN"},
    "PEGMATITE":   {"PEGMATITE", "PEGMATITE-LCT", "PEGMATITE-NYF", "PEGMATITE-REE"},
    "U":           {"U-SANDSTONE", "U-UNCONFORMITY", "U-ALBITITE", "U-VEIN", "U-PHOSPHATE"},
    "LATERITE":    {"LATERITE-NI", "LATERITE-REE", "LATERITE-AU", "NI-LATERITE", "RESIDUAL-MN"},
    "SEDIMENTARY": {"BIF-FE", "SEDIMENTARY-MN", "SEDIMENTARY-P", "EVAPORITE",
                    "COAL", "GRAPHITE", "BAUXITE"},
    "CU-SEDIMENT": {"KUPFERSCHIEFER", "SANDSTONE-CU", "SEDIMENT-CU"},
    "PLACER":      {"PLACER", "PLACER-TI-ZR", "PLACER-TIN"},
    "GREISEN":     {"GREISEN", "GREISEN-W-SN", "GREISEN-SN", "GREISEN-W"},
    "VEIN":        {"VEIN-AU", "VEIN-AG", "VEIN-CU", "VEIN-PB-ZN", "VEIN-SN-W",
                    "VEIN-SN", "FIVE-ELEMENT"},
    "DIAMOND":     {"KIMBERLITE", "LAMPROITE-DIAMOND"},
}

def family_of(dt: str) -> str | None:
    if not dt:
        return None
    dt = dt.upper()
    for fam, members in FAMILY_MAP.items():
        if dt in {m.upper() for m in members}:
            return fam
    return dt  # 不在映射中，用自身作为族群

def score_match(predicted: str, expected: str) -> float:
    """0=不匹配, 0.5=同族, 1.0=完全匹配（规范化后）"""
    if not predicted or not expected:
        return 0.0
    p = predicted.upper().strip()
    e = expected.upper().strip()
    # 直接完全匹配
    if p == e:
        return 1.0
    # 旧版非规范写法归一化（P1 实施前的遗留形式）
    NORMALIZE = {
        "PORPHYRY CU": "PORPHYRY-CU",
        "PORPHYRY AU": "PORPHYRY-AU",
        "PORPHYRY CU-AU": "PORPHYRY-CU-AU",
        "MAGMATIC CU-NI-PGE": "NI-CU-PGE",
        "MAGMATIC NI-CU": "NI-CU",
        "MAGMATIC NI-CU-PGE": "NI-CU-PGE",
        "LCT PEGMATITE": "PEGMATITE-LCT",
        "NYF PEGMATITE": "PEGMATITE-NYF",
        "REE-REGOLITH": "LATERITE-REE",
        "REE REGOLITH": "LATERITE-REE",
        "SANDSTONE-U": "U-SANDSTONE",
        "HOT SPRING AU": "EPITHERMAL-LS",
        "HS-EPITH": "EPITHERMAL-HS",
        "LS-EPITH": "EPITHERMAL-LS",
        "MUM-NICU": "NI-CU",
    }
    p_norm = NORMALIZE.get(p, p)
    e_norm = NORMALIZE.get(e, e)
    if p_norm == e_norm:
        return 1.0
    if family_of(p_norm) and family_of(p_norm) == family_of(e_norm):
        return 0.5
    return 0.0


def load_famous_deposits():
    """加载 famous_deposits 数据库"""
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from famous_deposits_database import FAMOUS_DEPOSITS
    # 统一为大写 key，便于模糊匹配
    return {k.upper(): v for k, v in FAMOUS_DEPOSITS.items()}


def match_reference_deposits(record: dict, famous: dict) -> list[dict]:
    """
    从 reference_deposits 字段匹配 famous_deposits 数据库。
    返回匹配到的 [{name, expected_type, predicted_type, score}]
    """
    ref_deps = record.get("reference_deposits") or []
    if not ref_deps:
        return []
    matches = []
    for rd in ref_deps:
        name = rd.get("name", "")
        name_upper = name.upper()
        # 精确匹配
        if name_upper in famous:
            expected = famous[name_upper].get("type", "")
            predicted = record.get("deposit_type") or ""
            s = score_match(predicted, expected)
            matches.append({"ref_deposit": name, "expected_type": expected,
                             "predicted_type": predicted, "score": s})
        else:
            # 部分匹配（子串）
            for fk, fv in famous.items():
                if name_upper in fk or fk in name_upper:
                    expected = fv.get("type", "")
                    predicted = record.get("deposit_type") or ""
                    s = score_match(predicted, expected)
                    matches.append({"ref_deposit": name, "famous_key": fk.title(),
                                    "expected_type": expected,
                                    "predicted_type": predicted, "score": s})
                    break
    return matches


def is_tibet_porphyry(record: dict) -> bool:
    """判断是否为西藏/Gangdese/Sanjiang 斑岩铜矿相关论文"""
    text = json.dumps(record, ensure_ascii=False).lower()
    tibet_keywords = ["tibet", "gangdese", "sanjiang", "lhasa", "tethyan", "qulong",
                      "jiama", "yulong", "驱龙", "甲玛", "玉龙", "西藏", "冈底斯",
                      "三江", "特提斯", "雅江", "yarlung", "post-collisional porphyry"]
    has_tibet = any(kw in text for kw in tibet_keywords)
    dt = (record.get("deposit_type") or "").upper()
    has_porphyry = "PORPHYRY" in dt or "porphyry" in text
    return has_tibet and has_porphyry


def build_check_line(paper_id: str, record: dict) -> dict:
    """构建一条人工 check 记录"""
    return {
        "paper_id": paper_id,
        "deposit_type_extracted": record.get("deposit_type"),
        "deposit_type_conf": record.get("deposit_type_conf"),
        "deposit_type_evidence": (record.get("deposit_type_evidence") or "")[:300],
        "countries": record.get("countries"),
        "metallogenic_belt": record.get("metallogenic_belt"),
        "coordinates": record.get("coordinates"),
        "is_primary_research": record.get("is_primary_research"),
        "reference_deposits": record.get("reference_deposits"),
        "host_rocks": record.get("host_rocks"),
        "alteration": record.get("alteration"),
    }


def run_eval(pilot_file: str, out_dir: str):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    data = json.load(open(pilot_file))
    famous = load_famous_deposits()

    auto_scores = []
    tibet_checks = []
    no_match = []
    null_analysis = []

    for item in data:
        paper_id = item.get("paper_id", "")
        rec = item.get("extracted") or item

        # 西藏斑岩铜矿 → 人工 check 清单
        if is_tibet_porphyry(rec):
            tibet_checks.append(build_check_line(paper_id, rec))

        # null 语义分析
        if rec.get("deposit_type") is None:
            null_reason = rec.get("deposit_type_null_reason", "MISSING_FIELD")
            null_analysis.append({
                "paper_id": paper_id,
                "deposit_class": rec.get("deposit_class"),
                "null_reason": null_reason,
            })

        # 自动匹配评测（通过参考矿床比对）
        matches = match_reference_deposits(rec, famous)
        if matches:
            best_score = max(m["score"] for m in matches)
            auto_scores.append({
                "paper_id": paper_id,
                "deposit_type": rec.get("deposit_type"),
                "matches": matches,
                "best_score": best_score,
            })
        else:
            no_match.append(paper_id)

    # 汇总统计
    if auto_scores:
        avg_score = sum(s["best_score"] for s in auto_scores) / len(auto_scores)
        perfect = sum(1 for s in auto_scores if s["best_score"] == 1.0)
        family = sum(1 for s in auto_scores if s["best_score"] == 0.5)
        wrong = sum(1 for s in auto_scores if s["best_score"] == 0.0)
    else:
        avg_score = perfect = family = wrong = 0

    report = {
        "total_papers": len(data),
        "auto_validated": len(auto_scores),
        "no_reference_match": len(no_match),
        "null_deposit_type": len(null_analysis),
        "tibet_porphyry_for_check": len(tibet_checks),
        "auto_scores": {
            "avg": round(avg_score, 3),
            "perfect_match_1.0": perfect,
            "family_match_0.5": family,
            "wrong_0.0": wrong,
        },
        "details": auto_scores,
        "null_analysis": null_analysis,
    }

    # 写报告
    report_file = out / "eval_report.json"
    json.dump(report, open(report_file, "w"), ensure_ascii=False, indent=2)
    print(f"\n{'='*60}")
    print(f"Pipeline v4 评测报告")
    print(f"{'='*60}")
    print(f"总论文数:       {report['total_papers']}")
    print(f"自动验证 (参考矿床匹配): {report['auto_validated']}")
    print(f"  完全匹配(1.0): {perfect}")
    print(f"  同族匹配(0.5): {family}")
    print(f"  不匹配 (0.0): {wrong}")
    print(f"  平均得分:      {avg_score:.3f}")
    print(f"无参考矿床可匹配: {len(no_match)}")
    print(f"deposit_type=null: {len(null_analysis)}")
    print(f"西藏斑岩铜矿 check: {len(tibet_checks)} 篇")
    print(f"报告: {report_file}")

    # 写西藏斑岩铜矿 check 清单 (Markdown)
    if tibet_checks:
        md_file = out / "TIBET_PORPHYRY_CHECK.md"
        lines = ["# 西藏斑岩铜矿 — 人工 Check 清单\n",
                 f"> 共 {len(tibet_checks)} 篇，请确认 deposit_type / metallogenic_belt / coordinates 是否正确\n",
                 "> **如何 check**：阅读 deposit_type_evidence，判断提取是否符合实际；",
                 "> 打 ✅ 正确 / ❌ 错误 / ⚠️ 部分正确\n\n"]
        for i, c in enumerate(tibet_checks, 1):
            lines.append(f"## [{i}] {c['paper_id']}\n")
            lines.append(f"- **deposit_type**: `{c['deposit_type_extracted']}` (conf={c['deposit_type_conf']})\n")
            lines.append(f"- **metallogenic_belt**: {c['metallogenic_belt']}\n")
            lines.append(f"- **countries**: {c['countries']}\n")
            coord = c['coordinates']
            if coord:
                lines.append(f"- **coordinates**: lat={coord.get('latitude')}, lon={coord.get('longitude')} "
                             f"[{coord.get('precision')}] conf={coord.get('confidence')} "
                             f"方法={coord.get('extraction_method')}\n")
            else:
                lines.append(f"- **coordinates**: null\n")
            lines.append(f"- **host_rocks**: {c['host_rocks']}\n")
            lines.append(f"- **alteration**: {c['alteration']}\n")
            if c['reference_deposits']:
                lines.append(f"- **reference_deposits**: {[r.get('name') for r in c['reference_deposits']]}\n")
            lines.append(f"- **evidence**: {c['deposit_type_evidence']}\n")
            lines.append(f"\n**你的判断**: [ ] ✅ 正确  [ ] ❌ 错误  [ ] ⚠️ 部分正确\n")
            lines.append(f"**备注**: \n\n---\n\n")
        md_file.write_text("".join(lines), encoding="utf-8")
        print(f"西藏斑岩铜矿 check 清单: {md_file}")

    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pilot_file", help="pilot 结果 JSON 文件")
    ap.add_argument("--out-dir", default="/root/autodl-tmp/pipeline-v4/eval_output")
    args = ap.parse_args()
    run_eval(args.pilot_file, args.out_dir)
