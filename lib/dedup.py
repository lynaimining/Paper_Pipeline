#!/usr/bin/env python3
"""
P1-F: Content-hash 去重模块
基于内容哈希去重（排除paper_id）
"""
import json
import hashlib
import re
from pathlib import Path
from collections import defaultdict


def content_hash(record):
    """
    计算记录的内容哈希（排除paper_id和gate字段）

    Args:
        record: 记录字典

    Returns:
        str: MD5哈希值
    """
    # 排除paper_id和gate相关字段
    content = {k: v for k, v in record.items()
               if k not in ["paper_id", "_gate_result", "_gate_flags", "_gate_detail"]}

    # 排序后序列化
    content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content_str.encode()).hexdigest()


def deduplicate(input_data):
    """
    去重：保留每组重复内容的代表

    策略：
    1. 按content-hash分组
    2. 每组保留一个代表：
       - 优先无后缀的paper_id（如 "2303" > "2303(1)"）
       - 其次保留第一个

    Args:
        input_data: list of records

    Returns:
        dict: {
            "unique": [...],  # 去重后的记录
            "deduped_ids": [...],  # 被去重的paper_id
            "duplicate_groups": {...}  # 重复组详情
        }
    """
    # 按hash分组
    hash_to_records = defaultdict(list)
    for record in input_data:
        h = content_hash(record)
        hash_to_records[h].append(record)

    # 去重
    unique = []
    deduped_ids = []
    duplicate_groups = {}

    for h, records in hash_to_records.items():
        if len(records) == 1:
            # 唯一记录，直接保留
            unique.append(records[0])
        else:
            # 重复记录，选择代表
            paper_ids = [r.get("paper_id") for r in records]

            # 策略：优先无后缀者
            no_suffix = [r for r in records if not re.search(r'\(\d+\)$', r.get("paper_id", ""))]
            with_suffix = [r for r in records if re.search(r'\(\d+\)$', r.get("paper_id", ""))]

            if no_suffix:
                keeper = no_suffix[0]
                removed = with_suffix + no_suffix[1:]
            else:
                keeper = records[0]
                removed = records[1:]

            unique.append(keeper)
            deduped_ids.extend([r.get("paper_id") for r in removed])

            # 记录重复组
            duplicate_groups[h] = {
                "kept": keeper.get("paper_id"),
                "removed": [r.get("paper_id") for r in removed],
                "count": len(records)
            }

    return {
        "unique": unique,
        "deduped_ids": deduped_ids,
        "duplicate_groups": duplicate_groups
    }


def deduplicate_file(input_file, output_file, report_file=None):
    """
    从文件读取数据，去重后写入

    Args:
        input_file: 输入JSON文件
        output_file: 输出JSON文件（去重后）
        report_file: 去重报告文件 (optional)

    Returns:
        dict: 去重统计
    """
    with open(input_file) as f:
        input_data = json.load(f)

    result = deduplicate(input_data)

    # 写入去重后数据
    with open(output_file, "w") as f:
        json.dump(result["unique"], f, indent=2, ensure_ascii=False)

    # 写入报告
    if report_file:
        report = {
            "input_count": len(input_data),
            "unique_count": len(result["unique"]),
            "deduped_count": len(result["deduped_ids"]),
            "duplicate_groups": len(result["duplicate_groups"]),
            "deduped_ids": result["deduped_ids"],
            "duplicate_groups": result["duplicate_groups"]
        }
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

    return {
        "input": len(input_data),
        "unique": len(result["unique"]),
        "deduped": len(result["deduped_ids"]),
        "groups": len(result["duplicate_groups"])
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python dedup.py <input.json> <output.json> [report.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    report_file = sys.argv[3] if len(sys.argv) > 3 else None

    stats = deduplicate_file(input_file, output_file, report_file)

    print("=" * 70)
    print("去重完成")
    print("=" * 70)
    print(f"输入: {stats['input']} 条")
    print(f"去重: {stats['deduped']} 条 ({stats['groups']} 组)")
    print(f"输出: {stats['unique']} 条")
    print(f"输出: {output_file}")
    if report_file:
        print(f"报告: {report_file}")
