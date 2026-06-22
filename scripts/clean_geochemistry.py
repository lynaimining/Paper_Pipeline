#!/usr/bin/env python3
"""
后处理清洗脚本 - 清除geochemistry空结构
"""
import json
import sys
from pathlib import Path


def clean_geochemistry(result):
    """清除geochemistry空结构，替换为null"""
    g = result.get('geochemistry')

    if g and isinstance(g, dict):
        has_data = False

        # 检查trace_elements
        te = g.get('trace_elements')
        if te and isinstance(te, dict):
            if te.get('enriched') or te.get('depleted'):
                has_data = True

        # 检查isotopes
        iso = g.get('isotopes')
        if iso and isinstance(iso, dict) and len(iso) > 0:
            has_data = True

        # 检查fluid_inclusion
        fi = g.get('fluid_inclusion')
        if fi and isinstance(fi, dict) and len(fi) > 0:
            has_data = True

        # 如果没有实质数据，替换为null
        if not has_data:
            result['geochemistry'] = None

    return result


def clean_batch(results):
    """批量清洗"""
    cleaned = 0
    for result in results:
        if 'extracted' in result:
            before = result['extracted'].get('geochemistry')
            clean_geochemistry(result['extracted'])
            after = result['extracted'].get('geochemistry')

            if before is not None and after is None:
                cleaned += 1
        else:
            before = result.get('geochemistry')
            clean_geochemistry(result)
            after = result.get('geochemistry')

            if before is not None and after is None:
                cleaned += 1

    return cleaned


def main():
    if len(sys.argv) < 2:
        print("用法: python clean_geochemistry.py <input.json> [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.json', '_cleaned.json')

    print("=" * 80)
    print("Geochemistry空结构清洗")
    print("=" * 80)
    print()

    # 读取
    with open(input_file) as f:
        data = json.load(f)

    total = len(data)
    print(f"输入样本: {total}篇")

    # 清洗
    cleaned = clean_batch(data)

    # 保存
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"清洗空结构: {cleaned}篇 ({cleaned/total*100:.1f}%)")
    print(f"输出文件: {output_file}")
    print()
    print("✅ 完成")


if __name__ == "__main__":
    main()
