#!/usr/bin/env python3
"""
著名矿床坐标匹配 - 使用USGS MRDS大型数据库
覆盖102,555个矿床
"""
import json
import sys
from pathlib import Path

# 加载MRDS数据库
MRDS_DB_PATH = Path(__file__).parent / "mrds_deposits.json"
_mrds_db = None


def load_mrds_db():
    global _mrds_db
    if _mrds_db is None:
        if MRDS_DB_PATH.exists():
            with open(MRDS_DB_PATH) as f:
                _mrds_db = json.load(f)
            print(f"✅ 加载USGS MRDS数据库: {len(_mrds_db):,}个矿床")
        else:
            print(f"⚠️  MRDS数据库不存在: {MRDS_DB_PATH}")
            _mrds_db = {}
    return _mrds_db


def match_famous_deposit(result):
    """
    匹配著名矿床坐标
    优先级：paper_id中的矿床名 > metallogenic_belt > paper_id模糊匹配
    """
    db = load_mrds_db()
    if not db:
        return False

    paper_id = (result.get('paper_id') or '').lower()
    belt = (result.get('metallogenic_belt') or '').lower()
    countries = [c.lower() for c in (result.get('countries') or [])]

    if result.get('coordinates'):
        return False

    # 建立候选集：paper_id + belt中可能的矿床名词
    candidates = []

    # 从paper_id提取可能的矿床名称词
    words = paper_id.replace('_', ' ').replace('-', ' ').split()
    for word in words:
        if len(word) > 4:  # 过滤短词
            candidates.append(word)

    # 从belt提取
    belt_words = belt.replace(',', ' ').split()
    for word in belt_words:
        if len(word) > 4:
            candidates.append(word)

    # 在MRDS数据库中查找匹配
    best_match = None
    best_score = 0

    for deposit_name, deposit_info in db.items():
        deposit_lower = deposit_name.lower()

        for candidate in candidates:
            if candidate in deposit_lower or deposit_lower in candidate:
                # 验证国家（如果有）
                if countries and deposit_info.get('country'):
                    dep_country = deposit_info['country'].lower()
                    if not any(c in dep_country or dep_country in c for c in countries):
                        continue

                # 计算匹配分数
                score = len(candidate) / max(len(deposit_lower), 1)
                if score > best_score:
                    best_score = score
                    best_match = (deposit_name, deposit_info)

    if best_match and best_score > 0.4:
        name, info = best_match
        result['coordinates'] = {
            "latitude": info['lat'],
            "longitude": info['lon'],
            "precision": "矿区级",
            "source": f"USGS MRDS-{name}",
            "confidence": min(0.9, best_score + 0.3),
            "extraction_method": "USGS MRDS数据库匹配"
        }
        return True

    return False


def match_batch(results):
    matched = 0
    for result in results:
        r = result.get('extracted') or result
        if match_famous_deposit(r):
            matched += 1
    return matched


def main():
    if len(sys.argv) < 2:
        print("用法: python match_famous_deposits.py <input.json> [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.json', '_with_mrds.json')

    print("=" * 80)
    print("USGS MRDS著名矿床坐标匹配")
    print("=" * 80)
    print()

    with open(input_file) as f:
        data = json.load(f)

    total = len(data)
    before = sum(1 for r in data if (r.get('extracted') or r).get('coordinates'))

    print(f"输入样本: {total}篇")
    print(f"已有坐标: {before}篇 ({before/total*100:.1f}%)")
    print()

    matched = match_batch(data)

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
