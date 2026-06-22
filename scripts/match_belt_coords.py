#!/usr/bin/env python3
"""
地质带/盆地坐标匹配脚本
用 belt_coords_db.py 中的质心库为缺坐标记录补充坐标
"""
import json, sys, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from belt_coords_db import BELT_COORDS

# 构建展开的别名索引（小写）
_INDEX = {}
for canonical, info in BELT_COORDS.items():
    _INDEX[canonical.lower()] = (canonical, info)
    for alias in info.get("alias", []):
        _INDEX[alias.lower()] = (canonical, info)


def _normalize(text):
    """标准化文本：小写 + 去多余空格"""
    return re.sub(r'\s+', ' ', text.strip().lower())


def match_belt_coord(result):
    """返回 True 表示成功补充坐标"""
    if result.get("coordinates"):
        return False

    belt = _normalize(result.get("metallogenic_belt") or "")
    if not belt:
        return False

    # 精确匹配
    if belt in _INDEX:
        canonical, info = _INDEX[belt]
        _apply(result, canonical, info, "exact")
        return True

    # 包含匹配（belt文本里含有索引key，或索引key含在belt里）
    best = None
    best_len = 0
    for key, (canonical, info) in _INDEX.items():
        if key in belt or belt in key:
            if len(key) > best_len:
                best_len = len(key)
                best = (canonical, info)

    if best:
        _apply(result, best[0], best[1], "contains")
        return True

    return False


def _apply(result, canonical, info, method):
    result["coordinates"] = {
        "latitude": info["lat"],
        "longitude": info["lon"],
        "precision": "地质带级",
        "source": f"地质带库-{canonical}",
        "confidence": 0.75 if method == "exact" else 0.65,
        "extraction_method": "地质带坐标库匹配",
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python match_belt_coords.py <input.json> [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(".json", "_with_belt.json")

    with open(input_file) as f:
        data = json.load(f)

    total = len(data)
    before = sum(1 for r in data if (r.get("extracted") or r).get("coordinates"))

    matched = 0
    for r in data:
        rec = r.get("extracted") or r
        if match_belt_coord(rec):
            matched += 1

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    after = sum(1 for r in data if (r.get("extracted") or r).get("coordinates"))

    print(f"输入: {total}篇 | 原有坐标: {before} | 新增: {matched} | 现有: {after} ({after/total*100:.1f}%)")
    print(f"输出: {output_file}")


if __name__ == "__main__":
    main()
