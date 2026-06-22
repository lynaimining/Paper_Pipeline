#!/usr/bin/env python3
"""
坐标一致性校验模块
验证 coordinates 与 countries/metallogenic_belt 的地理一致性
"""
import json
from typing import Dict, List, Tuple, Optional


# 国家边界（简化版，粗略范围）
COUNTRY_BOUNDS = {
    "Australia": {"lat": (-44, -10), "lon": (113, 154)},
    "China": {"lat": (18, 54), "lon": (73, 135)},
    "USA": {"lat": (25, 49), "lon": (-125, -66)},
    "Canada": {"lat": (42, 83), "lon": (-141, -52)},
    "Brazil": {"lat": (-34, 5), "lon": (-74, -35)},
    "Russia": {"lat": (41, 82), "lon": (19, 180)},
    "South Africa": {"lat": (-35, -22), "lon": (16, 33)},
    "Peru": {"lat": (-18, 0), "lon": (-81, -68)},
    "Chile": {"lat": (-56, -17), "lon": (-76, -66)},
    "Poland": {"lat": (49, 55), "lon": (14, 24)},
    "Iran": {"lat": (25, 40), "lon": (44, 64)},
    "Turkey": {"lat": (36, 42), "lon": (26, 45)},
    "Mexico": {"lat": (14, 33), "lon": (-118, -86)},
    "Argentina": {"lat": (-55, -22), "lon": (-73, -53)},
    "Kazakhstan": {"lat": (41, 55), "lon": (47, 87)},
    "Mongolia": {"lat": (42, 52), "lon": (88, 120)},
    "India": {"lat": (8, 35), "lon": (68, 97)},
    "Egypt": {"lat": (22, 32), "lon": (25, 37)},
    "Saudi Arabia": {"lat": (16, 32), "lon": (34, 56)},
    "Finland": {"lat": (60, 70), "lon": (20, 32)},
    "Sweden": {"lat": (55, 69), "lon": (11, 24)},
    "Norway": {"lat": (58, 71), "lon": (4, 31)},
    "Greenland": {"lat": (60, 84), "lon": (-73, -12)},
    "Rwanda": {"lat": (-3, -1), "lon": (29, 31)},
    "DR Congo": {"lat": (-13, 5), "lon": (12, 31)},
}

# 成矿带/地质单元粗略位置（lat, lon中心点 + 半径km）
METALLOGENIC_BELT_LOCATIONS = {
    "Pine Creek Orogen": {"center": (-13.5, 131.5), "radius_km": 200},
    "Jiaodong": {"center": (37.5, 120.5), "radius_km": 300},
    "Yilgarn Craton": {"center": (-30, 120), "radius_km": 500},
    "North China Craton": {"center": (39, 117), "radius_km": 800},
    "Abitibi": {"center": (48.5, -78), "radius_km": 300},
    "Witwatersrand": {"center": (-26.5, 27.5), "radius_km": 150},
}


def validate_coordinates(record: dict) -> dict:
    """
    校验坐标一致性

    Returns:
        {
            "valid": bool,
            "errors": [str],
            "warnings": [str],
            "suggestions": [str]
        }
    """
    coords = record.get("coordinates")
    countries = record.get("countries", [])
    metallogenic_belt = record.get("metallogenic_belt", "")

    errors = []
    warnings = []
    suggestions = []

    if not coords:
        return {"valid": True, "errors": [], "warnings": ["无坐标"], "suggestions": []}

    lat = coords.get("latitude")
    lon = coords.get("longitude")

    # 1. 基本范围检查
    if lat is None or lon is None:
        errors.append("坐标缺失经纬度值")
        return {"valid": False, "errors": errors, "warnings": [], "suggestions": []}

    if not (-90 <= lat <= 90):
        errors.append(f"纬度超出范围: {lat} (应在-90到90之间)")

    if not (-180 <= lon <= 180):
        errors.append(f"经度超出范围: {lon} (应在-180到180之间)")

    # 2. 国家一致性检查
    if countries:
        country_match = False
        for country in countries:
            if country in COUNTRY_BOUNDS:
                bounds = COUNTRY_BOUNDS[country]
                lat_range = bounds["lat"]
                lon_range = bounds["lon"]

                if lat_range[0] <= lat <= lat_range[1] and lon_range[0] <= lon <= lon_range[1]:
                    country_match = True
                    break

        if not country_match:
            matched_countries = []
            for country, bounds in COUNTRY_BOUNDS.items():
                lat_range = bounds["lat"]
                lon_range = bounds["lon"]
                if lat_range[0] <= lat <= lat_range[1] and lon_range[0] <= lon <= lon_range[1]:
                    matched_countries.append(country)

            if matched_countries:
                errors.append(
                    f"坐标({lat:.2f}, {lon:.2f})不在声称的国家{countries}内，"
                    f"实际位置可能是: {matched_countries}"
                )
            else:
                warnings.append(f"坐标({lat:.2f}, {lon:.2f})未匹配到已知国家范围")

    # 3. 成矿带一致性检查
    if metallogenic_belt:
        belt_match = False
        for belt_name, location in METALLOGENIC_BELT_LOCATIONS.items():
            if belt_name.lower() in metallogenic_belt.lower():
                center = location["center"]
                radius_km = location["radius_km"]

                # 简单距离计算（近似）
                lat_diff = abs(lat - center[0])
                lon_diff = abs(lon - center[1])
                dist_km = ((lat_diff * 111) ** 2 + (lon_diff * 111 * 0.8) ** 2) ** 0.5

                if dist_km <= radius_km:
                    belt_match = True
                else:
                    warnings.append(
                        f"坐标距离成矿带'{belt_name}'中心{dist_km:.0f}km，"
                        f"超出预期半径{radius_km}km"
                    )
                break

    # 4. 南北半球检查
    hemisphere_keywords = {
        "Northern": "北半球",
        "Southern": "南半球",
        "North": "北",
        "South": "南"
    }

    for keyword, expected in hemisphere_keywords.items():
        if keyword in metallogenic_belt or keyword in str(countries):
            if keyword in ["Northern", "North"] and lat < 0:
                warnings.append(f"成矿带/国家提到'{keyword}'（北），但纬度{lat}在南半球")
            elif keyword in ["Southern", "South"] and lat > 0:
                warnings.append(f"成矿带/国家提到'{keyword}'（南），但纬度{lat}在北半球")

    # 5. 置信度与精度一致性
    confidence = coords.get("confidence", 0)
    precision = coords.get("precision", "")

    if precision == "矿区级" and confidence < 0.8:
        warnings.append(f"矿区级精��但置信度偏低({confidence:.2f})")

    if precision == "省级" and confidence > 0.9:
        warnings.append(f"省级精度但置信度过高({confidence:.2f})，可能实际是矿区级")

    # 6. 建议
    if errors:
        suggestions.append("检查LLM提取的坐标是否正确，或手动修正")

    if warnings and not errors:
        suggestions.append("可能需要人工复核坐标准确性")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "suggestions": suggestions
    }


def batch_validate(results: List[dict]) -> dict:
    """批量校验，生成报告"""

    validated = []
    stats = {
        "total": len(results),
        "valid": 0,
        "has_errors": 0,
        "has_warnings": 0
    }

    for record in results:
        validation = validate_coordinates(record)
        validated.append({
            "paper_id": record.get("paper_id"),
            "coordinates": record.get("coordinates"),
            "countries": record.get("countries"),
            "validation": validation
        })

        if validation["valid"]:
            stats["valid"] += 1
        if validation["errors"]:
            stats["has_errors"] += 1
        if validation["warnings"]:
            stats["has_warnings"] += 1

    return {
        "results": validated,
        "stats": stats
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python validate_coordinates.py <results.json>")
        sys.exit(1)

    input_file = sys.argv[1]

    with open(input_file) as f:
        data = json.load(f)

    # 提取extracted字段
    if isinstance(data, list) and len(data) > 0 and "extracted" in data[0]:
        records = [r["extracted"] for r in data]
    else:
        records = data

    # 批量校验
    report = batch_validate(records)

    # 打印报告
    print("=" * 80)
    print("坐标一致性校验报告")
    print("=" * 80)
    print()
    print(f"总样本: {report['stats']['total']} 篇")
    print(f"  有效: {report['stats']['valid']} 篇 ({report['stats']['valid']/report['stats']['total']*100:.1f}%)")
    print(f"  错误: {report['stats']['has_errors']} 篇")
    print(f"  警告: {report['stats']['has_warnings']} 篇")
    print()

    # 显示错误和警告
    for item in report["results"]:
        validation = item["validation"]
        if validation["errors"] or validation["warnings"]:
            print(f"论文: {item['paper_id'][:60]}")
            print(f"  国家: {item['countries']}")
            coords = item.get("coordinates")
            if coords:
                print(f"  坐标: ({coords.get('latitude'):.2f}, {coords.get('longitude'):.2f})")
                print(f"  精度: {coords.get('precision')} | 置信度: {coords.get('confidence')}")

            if validation["errors"]:
                print("  ❌ 错误:")
                for err in validation["errors"]:
                    print(f"     {err}")

            if validation["warnings"]:
                print("  ⚠️  警告:")
                for warn in validation["warnings"]:
                    print(f"     {warn}")

            if validation["suggestions"]:
                print("  💡 建议:")
                for sug in validation["suggestions"]:
                    print(f"     {sug}")

            print()

    # 保存报告
    output_file = input_file.replace(".json", "_validation.json")
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"详细报告已保存: {output_file}")
