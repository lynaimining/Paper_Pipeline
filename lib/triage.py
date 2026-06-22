#!/usr/bin/env python3
"""
P0-B: 三桶分流模块
将 gate 结果分流到 trusted / review / quarantine
"""
import json
from pathlib import Path


def triage(input_data, output_dir):
    """
    三桶分流：pass → trusted, warn → review, fail → quarantine

    Args:
        input_data: list of records
        output_dir: 输出目录

    Returns:
        dict: {
            "trusted": [...],
            "review": [...],
            "quarantine": [...],
            "stats": {...}
        }
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trusted = []
    review = []
    quarantine = []

    for record in input_data:
        gate_result = record.get("_gate_result", "pass")  # 默认pass

        # 剥离调试字段
        clean_record = {k: v for k, v in record.items() if not k.startswith("_gate_")}

        if gate_result == "pass":
            trusted.append(clean_record)
        elif gate_result == "warn":
            review.append(clean_record)
        elif gate_result == "fail":
            quarantine.append(clean_record)
        else:
            # 未知状态，保守放入review
            review.append(clean_record)

    # 写入文件
    with open(output_dir / "trusted.json", "w") as f:
        json.dump(trusted, f, indent=2, ensure_ascii=False)

    with open(output_dir / "review.json", "w") as f:
        json.dump(review, f, indent=2, ensure_ascii=False)

    with open(output_dir / "quarantine.json", "w") as f:
        json.dump(quarantine, f, indent=2, ensure_ascii=False)

    stats = {
        "input": len(input_data),
        "trusted": len(trusted),
        "review": len(review),
        "quarantine": len(quarantine),
        "output": len(trusted) + len(review) + len(quarantine)
    }

    with open(output_dir / "triage_stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    return {
        "trusted": trusted,
        "review": review,
        "quarantine": quarantine,
        "stats": stats
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python triage.py <input.json> <output_dir>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    with open(input_file) as f:
        data = json.load(f)

    result = triage(data, output_dir)

    print(f"三桶分流完成:")
    print(f"  输入: {result['stats']['input']} 条")
    print(f"  trusted: {result['stats']['trusted']} 条")
    print(f"  review: {result['stats']['review']} 条")
    print(f"  quarantine: {result['stats']['quarantine']} 条")
