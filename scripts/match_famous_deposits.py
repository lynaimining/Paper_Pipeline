#!/usr/bin/env python3
"""
著名矿床坐标库 - 100+世界著名矿床
数据来源：USGS, 各国地质调查局, 学术文献, 上市公司年报
"""
import json
import sys
from pathlib import Path

# 导入大型矿床数据库
from famous_deposits_database import FAMOUS_DEPOSITS


def match_famous_deposit(result):
    """匹配著名矿床坐标"""
    paper_id = (result.get('paper_id') or '').lower()
    belt = (result.get('metallogenic_belt') or '').lower()
    countries = [c.lower() for c in (result.get('countries') or [])]

    matched = False
    for deposit_name, coords in FAMOUS_DEPOSITS.items():
        deposit_lower = deposit_name.lower()

        # 匹配条件：paper_id或metallogenic_belt中包含矿床名
        if deposit_lower in paper_id or deposit_lower in belt:
            # 验证国家一致（如果有）
            if countries and coords['country'].lower() not in ' '.join(countries):
                continue

            # 补充coordinates
            if not result.get('coordinates'):
                result['coordinates'] = {
                    "latitude": coords['lat'],
                    "longitude": coords['lon'],
                    "precision": "矿床级",
                    "source": f"著名矿床库-{deposit_name}",
                    "confidence": 0.95,
                    "extraction_method": "著名矿床库匹配"
                }
                matched = True
                break

    return matched


def match_batch(results):
    """批量匹配"""
    matched = 0
    for result in results:
        if 'extracted' in result:
            if match_famous_deposit(result['extracted']):
                matched += 1
        else:
            if match_famous_deposit(result):
                matched += 1

    return matched


def main():
    if len(sys.argv) < 2:
        print("用法: python match_famous_deposits.py <input.json> [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.json', '_with_famous.json')

    print("=" * 80)
    print("著名矿床坐标匹配")
    print("=" * 80)
    print()
    print(f"矿床库规模: {len(FAMOUS_DEPOSITS)}个著名矿床")
    print()

    # 读取
    with open(input_file) as f:
        data = json.load(f)

    total = len(data)
    before = sum(1 for r in data if (r.get('extracted') or r).get('coordinates'))

    print(f"输入样本: {total}篇")
    print(f"已有坐标: {before}篇 ({before/total*100:.1f}%)")
    print()

    # 匹配
    matched = match_batch(data)

    # 保存
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    after = sum(1 for r in data if (r.get('extracted') or r).get('coordinates'))

    print(f"新增坐标: {matched}篇")
    print(f"现有坐标: {after}篇 ({after/total*100:.1f}%)")
    print(f"输出文件: {output_file}")
    print()
    print("✅ 完成")


if __name__ == "__main__":
    main()
