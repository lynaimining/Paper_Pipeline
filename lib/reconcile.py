#!/usr/bin/env python3
"""
P0-C: 对账模块
验证数据守恒：输入 = trusted + review + quarantine + deduped
"""
import json
from pathlib import Path


def reconcile(input_data, trusted, review, quarantine, deduped_ids=None):
    """
    对账：验证数据守恒

    Args:
        input_data: 输入数据 (list)
        trusted: trusted桶数据 (list)
        review: review桶数据 (list)
        quarantine: quarantine桶数据 (list)
        deduped_ids: 去重的paper_id列表 (list, optional)

    Returns:
        dict: {
            "reconciled": bool,
            "input": int,
            "trusted": int,
            "review": int,
            "quarantine": int,
            "deduped": int,
            "output": int,
            "missing": list,
            "extra": list
        }
    """
    input_ids = {r.get("paper_id") for r in input_data}

    output_ids = set()
    for bucket in [trusted, review, quarantine]:
        for rec in bucket:
            output_ids.add(rec.get("paper_id"))

    # 加上去重的IDs
    if deduped_ids:
        output_ids.update(deduped_ids)

    # 检查守恒
    missing = input_ids - output_ids
    extra = output_ids - input_ids

    reconciled = (len(input_ids) == len(output_ids) and not missing and not extra)

    return {
        "reconciled": reconciled,
        "input": len(input_data),
        "trusted": len(trusted),
        "review": len(review),
        "quarantine": len(quarantine),
        "deduped": len(deduped_ids) if deduped_ids else 0,
        "output": len(output_ids),
        "missing": list(missing),
        "extra": list(extra)
    }


def reconcile_from_files(input_file, output_dir, deduped_file=None):
    """
    从文件读取数据并对账

    Args:
        input_file: 输入JSON文件
        output_dir: 输出目录（包含trusted/review/quarantine.json）
        deduped_file: 去重记录文件 (optional)

    Returns:
        dict: 对账结果

    Raises:
        RuntimeError: 对账失败
    """
    output_dir = Path(output_dir)

    # 读取输入
    with open(input_file) as f:
        input_data = json.load(f)

    # 读取三桶
    with open(output_dir / "trusted.json") as f:
        trusted = json.load(f)

    with open(output_dir / "review.json") as f:
        review = json.load(f)

    with open(output_dir / "quarantine.json") as f:
        quarantine = json.load(f)

    # 读取去重记录（如果有）
    deduped_ids = None
    if deduped_file and Path(deduped_file).exists():
        with open(deduped_file) as f:
            dedup_data = json.load(f)
            deduped_ids = dedup_data.get("deduped_ids", [])

    # 对账
    result = reconcile(input_data, trusted, review, quarantine, deduped_ids)

    # 写入对账报告
    with open(output_dir / "reconcile_report.json", "w") as f:
        json.dump(result, f, indent=2)

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python reconcile.py <input.json> <output_dir> [deduped.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]
    deduped_file = sys.argv[3] if len(sys.argv) > 3 else None

    result = reconcile_from_files(input_file, output_dir, deduped_file)

    print("=" * 70)
    print("对账报告")
    print("=" * 70)
    print(f"输入: {result['input']} 条")
    print(f"输出: trusted={result['trusted']} + review={result['review']} + quarantine={result['quarantine']} + deduped={result['deduped']} = {result['output']} 条")
    print(f"对账: {'✅ PASS' if result['reconciled'] else '❌ FAIL'}")

    if not result['reconciled']:
        if result['missing']:
            print(f"\n❌ 丢失 {len(result['missing'])} 条:")
            for pid in result['missing'][:5]:
                print(f"  - {pid}")
        if result['extra']:
            print(f"\n❌ 多出 {len(result['extra'])} 条:")
            for pid in result['extra'][:5]:
                print(f"  - {pid}")

        sys.exit(1)
    else:
        print("\n✅ 数据守恒验证通过")
