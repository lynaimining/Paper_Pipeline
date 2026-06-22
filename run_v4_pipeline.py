#!/usr/bin/env python3
"""
Pipeline v4 集成脚本
整合 P0-B/C 和 P1-D/E/F 到完整流程
"""
import sys
import json
from pathlib import Path

# 添加lib到路径
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from triage import triage
from reconcile import reconcile
from dedup import deduplicate
from sanitize import sanitize_paper_id
from verify_gate import verify_canonical_gate


def run_post_gate_processing(input_file, output_dir):
    """
    Gate后处理流程：
    1. 去重 (P1-F)
    2. 三桶分流 (P0-B)
    3. 对账 (P0-C)

    Args:
        input_file: gate输出的JSON文件（all_results.json）
        output_dir: 输出目录
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Pipeline v4 后处理")
    print("=" * 70)
    print(f"输入: {input_file}")
    print(f"输出: {output_dir}")
    print()

    # 加载数据
    with open(input_file) as f:
        data = json.load(f)

    print(f"加载数据: {len(data)} 条")
    print()

    # ========================================================================
    # Step 1: 去重 (P1-F)
    # ========================================================================
    print("Step 1: Content-hash 去重")
    print("-" * 70)

    dedup_result = deduplicate(data)

    deduped_data = dedup_result["unique"]
    deduped_ids = dedup_result["deduped_ids"]
    duplicate_groups = dedup_result["duplicate_groups"]

    print(f"  输入: {len(data)} 条")
    print(f"  去重: {len(deduped_ids)} 条 ({len(duplicate_groups)} 组)")
    print(f"  输出: {len(deduped_data)} 条")
    print()

    # 保存去重记录
    with open(output_dir / "dedup_report.json", "w") as f:
        json.dump({
            "deduped_ids": deduped_ids,
            "duplicate_groups": duplicate_groups,
            "stats": {
                "input": len(data),
                "unique": len(deduped_data),
                "deduped": len(deduped_ids),
                "groups": len(duplicate_groups)
            }
        }, f, indent=2)

    # ========================================================================
    # Step 2: 三桶分流 (P0-B)
    # ========================================================================
    print("Step 2: 三桶分流")
    print("-" * 70)

    triage_result = triage(deduped_data, output_dir)

    trusted = triage_result["trusted"]
    review = triage_result["review"]
    quarantine = triage_result["quarantine"]

    print(f"  输入: {len(deduped_data)} 条")
    print(f"  trusted: {len(trusted)} 条")
    print(f"  review: {len(review)} 条")
    print(f"  quarantine: {len(quarantine)} 条")
    print()

    # ========================================================================
    # Step 3: 对账 (P0-C)
    # ========================================================================
    print("Step 3: 对账验证")
    print("-" * 70)

    reconcile_result = reconcile(data, trusted, review, quarantine, deduped_ids)

    print(f"  输入: {reconcile_result['input']} 条")
    print(f"  输出: trusted={reconcile_result['trusted']} + review={reconcile_result['review']} + quarantine={reconcile_result['quarantine']} + deduped={reconcile_result['deduped']} = {reconcile_result['output']} 条")
    print(f"  对账: {'✅ PASS' if reconcile_result['reconciled'] else '❌ FAIL'}")
    print()

    # 保存对账报告
    with open(output_dir / "reconcile_report.json", "w") as f:
        json.dump(reconcile_result, f, indent=2)

    if not reconcile_result['reconciled']:
        print("❌ 对账失败！数据不守恒")
        if reconcile_result['missing']:
            print(f"   丢失 {len(reconcile_result['missing'])} 条:")
            for pid in reconcile_result['missing'][:5]:
                print(f"     - {pid}")
        if reconcile_result['extra']:
            print(f"   多出 {len(reconcile_result['extra'])} 条:")
            for pid in reconcile_result['extra'][:5]:
                print(f"     - {pid}")
        return False

    # ========================================================================
    # 汇总
    # ========================================================================
    print("=" * 70)
    print("✅ Pipeline v4 后处理完成")
    print("=" * 70)
    print()
    print("产出文件:")
    print(f"  - {output_dir}/trusted.json ({len(trusted)} 条)")
    print(f"  - {output_dir}/review.json ({len(review)} 条)")
    print(f"  - {output_dir}/quarantine.json ({len(quarantine)} 条)")
    print(f"  - {output_dir}/dedup_report.json")
    print(f"  - {output_dir}/triage_stats.json")
    print(f"  - {output_dir}/reconcile_report.json")
    print()

    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline v4 后处理")
    parser.add_argument("input_file", help="gate输出的JSON文件（all_results.json）")
    parser.add_argument("output_dir", help="输出目录")
    parser.add_argument("--verify-gate", action="store_true", help="部署前验证gate版本")

    args = parser.parse_args()

    # 可选：验证gate版本
    if args.verify_gate:
        try:
            print("验证 gate 版本...")
            verify_canonical_gate(Path(__file__).parent / "scripts" / "gate_lite.py")
            print()
        except RuntimeError as e:
            print(f"{e}")
            sys.exit(1)

    # 运行后处理
    success = run_post_gate_processing(args.input_file, args.output_dir)

    sys.exit(0 if success else 1)
