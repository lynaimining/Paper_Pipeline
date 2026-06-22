#!/usr/bin/env python3
"""
F6 确定性基准回归测试（书中 F6 的直接实现）
─────────────────────────────────────────
做什么：对 famous_deposits 库里每个已知矿床，在提取结果里查找对应论文，
        检查 deposit_type 是否和预期一致。词表改了之后每次都跑，退化立刻可见。

用法：
  python regression_test.py <trusted_processed.json> [--strict]

  --strict  完全匹配才算通过（默认：同族匹配也算通过）

输出：
  回归报告打印到 stdout
  regression_report.json 写入 <输入文件同目录>
"""
import sys, json, argparse
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from famous_deposits_database import FAMOUS_DEPOSITS
from eval import FAMILY_MAP, score_match   # 复用 eval.py 里的评分逻辑


def build_deposit_name_index(data: list[dict]) -> dict:
    """从 reference_deposits 和 metallogenic_belt 里建立矿床名→论文 的反向索引"""
    index = {}  # deposit_name_upper → [record]
    for r in data:
        # 1. reference_deposits 字段里的矿床名
        for rd in (r.get("reference_deposits") or []):
            name = rd.get("name", "").upper().strip()
            if name:
                index.setdefault(name, []).append(r)
        # 2. paper_id 本身（有些论文标题就是矿床名）
        pid_upper = r.get("paper_id", "").upper()
        for famous_name in FAMOUS_DEPOSITS:
            fn = famous_name.upper()
            if fn in pid_upper or fn in (r.get("metallogenic_belt") or "").upper():
                index.setdefault(fn, []).append(r)
    return index


def run_regression(trusted_file: str, strict: bool = False) -> dict:
    data = json.load(open(trusted_file))
    famous_upper = {k.upper(): v for k, v in FAMOUS_DEPOSITS.items()}

    # 建索引
    name_index = build_deposit_name_index(data)

    results = []
    tested = 0
    passed = 0
    failed = 0
    not_found = 0

    for dep_name, dep_info in FAMOUS_DEPOSITS.items():
        expected_type = dep_info.get("type", "")
        if not expected_type:
            continue

        dep_upper = dep_name.upper()
        matching_records = name_index.get(dep_upper, [])

        # 也做子串模糊匹配
        if not matching_records:
            for idx_name, records in name_index.items():
                if dep_upper in idx_name or idx_name in dep_upper:
                    matching_records.extend(records)
                    break

        if not matching_records:
            not_found += 1
            results.append({
                "deposit": dep_name,
                "expected": expected_type,
                "status": "not_found",
                "matched_papers": 0,
            })
            continue

        # 对找到的论文，取最高分
        best_score = 0.0
        best_record = None
        for r in matching_records:
            predicted = r.get("deposit_type") or ""
            s = score_match(predicted, expected_type)
            if strict:
                s = 1.0 if predicted.upper() == expected_type.upper() else 0.0
            if s > best_score:
                best_score = s
                best_record = r

        tested += 1
        status = "PASS" if best_score >= 0.5 else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1

        results.append({
            "deposit": dep_name,
            "expected": expected_type,
            "predicted": best_record.get("deposit_type") if best_record else None,
            "score": best_score,
            "status": status,
            "paper_id": best_record.get("paper_id", "")[:60] if best_record else None,
            "matched_papers": len(matching_records),
        })

    # 排序：FAIL 在前
    results.sort(key=lambda x: (x["status"] != "FAIL", x["deposit"]))

    report = {
        "total_in_db": len(FAMOUS_DEPOSITS),
        "testable": tested,
        "not_found": not_found,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / tested, 3) if tested else 0,
        "strict_mode": strict,
        "results": results,
    }

    # 写报告
    out_path = Path(trusted_file).parent / "regression_report.json"
    json.dump(report, open(out_path, "w"), ensure_ascii=False, indent=2)

    # 打印摘要
    print("=" * 60)
    print("F6 确定性基准回归测试")
    print("=" * 60)
    print(f"famous_deposits 库: {report['total_in_db']} 条")
    print(f"可测试（找到对应论文）: {tested}")
    print(f"未找到对应论文: {not_found}")
    print(f"通过: {passed} ({report['pass_rate']:.0%})")
    print(f"失败: {failed}")
    print(f"模式: {'严格匹配' if strict else '同族匹配'}")
    print()

    if failed > 0:
        print("❌ 失败项（需要关注）:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  {r['deposit']:25s} 期望={r['expected']:20s} 实际={r.get('predicted','?')}")
    print()

    # 分类型通过率
    type_pass = Counter()
    type_total = Counter()
    for r in results:
        if r["status"] in ("PASS", "FAIL"):
            t = r["expected"].split("-")[0]
            type_total[t] += 1
            if r["status"] == "PASS":
                type_pass[t] += 1
    print("按类型通过率:")
    for t, total in sorted(type_total.items(), key=lambda x: -x[1]):
        p = type_pass.get(t, 0)
        bar = "✅" if p == total else ("⚠️" if p > 0 else "❌")
        print(f"  {bar} {t:15s} {p}/{total}")

    print(f"\n完整报告: {out_path}")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("trusted_file", help="trusted_processed.json 路径")
    ap.add_argument("--strict", action="store_true", help="严格匹配（默认同族匹配）")
    args = ap.parse_args()
    run_regression(args.trusted_file, args.strict)
