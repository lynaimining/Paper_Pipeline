#!/usr/bin/env python3
"""
坐标一致性校验模块 V3 - 使用在线API
轻量级，无需本地数据，覆盖全球所有国家
"""
import json
from typing import Dict, List, Optional
import time

# 使用免费的Reverse Geocoding API
def get_country_from_coords(lat: float, lon: float) -> Optional[str]:
    """
    通过API获取坐标所在国家（免费，无需API key）

    API: bigdatacloud.net (免费10000次/月)
    """
    try:
        import requests
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=en"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('countryName')
    except Exception as e:
        print(f"  ⚠️  API调用失败: {e}")
    return None


class CoordinateValidatorV3:
    """坐标校验器 V3（在线API）"""

    def __init__(self, use_api: bool = False):
        """
        Args:
            use_api: 是否使用在线API（默认False，避免频繁调用）
        """
        self.use_api = use_api
        self.api_cache = {}  # 缓存API结果

    def validate_record(self, record: dict) -> dict:
        """校验单条记录"""
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
            errors.append(f"纬度超出范围: {lat}")

        if not (-180 <= lon <= 180):
            errors.append(f"经度超出范围: {lon}")

        # 2. 国家一致性（可选API校验）
        if countries and self.use_api:
            cache_key = f"{lat:.2f},{lon:.2f}"

            if cache_key in self.api_cache:
                actual_country = self.api_cache[cache_key]
            else:
                actual_country = get_country_from_coords(lat, lon)
                self.api_cache[cache_key] = actual_country
                time.sleep(0.5)  # API限速

            if actual_country:
                matched = False
                for claimed_country in countries:
                    if self._country_match(claimed_country, actual_country):
                        matched = True
                        suggestions.append(f"✅ 坐标在{actual_country}境内，验证通过")
                        break

                if not matched:
                    errors.append(
                        f"坐标({lat:.2f}, {lon:.2f})不在声称的国家{countries}内，"
                        f"实际位置: {actual_country}"
                    )

        # 3. 南北半球一致性
        text = f"{metallogenic_belt} {countries}"
        if "Northern" in text or "North" in text:
            if lat < 0:
                warnings.append(f"提到'North/Northern'，但纬度{lat}在南半球")
        if "Southern" in text or "South" in text:
            if lat > 0 and "South Africa" not in text and "South Korea" not in text:
                warnings.append(f"提到'South/Southern'，但纬度{lat}在北半球")

        # 4. 置信度与精度匹配
        confidence = coords.get("confidence", 0)
        precision = coords.get("precision", "")

        if precision == "矿区级" and confidence < 0.8:
            warnings.append(f"矿区级精度但置信度偏低({confidence:.2f})")

        if precision == "省级" and confidence > 0.9:
            warnings.append(f"省级精度但置信度过高({confidence:.2f})")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "suggestions": suggestions
        }

    def _country_match(self, claimed: str, actual: str) -> bool:
        """国家名称匹配"""
        claimed_lower = claimed.lower().strip()
        actual_lower = actual.lower().strip()

        if claimed_lower == actual_lower:
            return True

        # 别名
        aliases = {
            'usa': ['united states', 'united states of america'],
            'uk': ['united kingdom'],
            'dr congo': ['democratic republic of the congo'],
            'tanzania': ['united republic of tanzania'],
            'russia': ['russian federation'],
        }

        for key, values in aliases.items():
            if claimed_lower in values or claimed_lower == key:
                if actual_lower in values or actual_lower == key:
                    return True

        return False


def batch_validate_v3(results: List[dict], use_api: bool = False) -> dict:
    """批量校验 V3"""

    validator = CoordinateValidatorV3(use_api=use_api)

    validated = []
    stats = {
        "total": len(results),
        "valid": 0,
        "has_errors": 0,
        "has_warnings": 0
    }

    for i, record in enumerate(results):
        if use_api and i % 5 == 0:
            print(f"  校验进度: {i}/{len(results)}...")

        validation = validator.validate_record(record)
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
    import argparse

    parser = argparse.ArgumentParser(description="坐标一致性校验 V3")
    parser.add_argument("input_file", help="输入JSON文件")
    parser.add_argument("--use-api", action="store_true", help="使用在线API验证（较慢）")
    args = parser.parse_args()

    with open(args.input_file) as f:
        data = json.load(f)

    # 提取数据
    if isinstance(data, list) and len(data) > 0 and "extracted" in data[0]:
        records = [r["extracted"] for r in data]
    else:
        records = data

    print("=" * 80)
    print("坐标一致性校验 V3")
    print("=" * 80)
    if args.use_api:
        print("⚠️  使用在线API验证（较慢，适合小样本）")
    else:
        print("快速模式（仅基本检查，不验证国家边界）")
    print()

    # 批量校验
    report = batch_validate_v3(records, use_api=args.use_api)

    # 打印报告
    print()
    print("=" * 80)
    print("校验报告")
    print("=" * 80)
    print()
    print(f"总样本: {report['stats']['total']} 篇")
    print(f"  ✅ 有效: {report['stats']['valid']} 篇 ({report['stats']['valid']/report['stats']['total']*100:.1f}%)")
    print(f"  ❌ 错误: {report['stats']['has_errors']} 篇")
    print(f"  ⚠️  警告: {report['stats']['has_warnings']} 篇")
    print()

    # 显示问题
    has_issues = False
    for item in report["results"]:
        validation = item["validation"]
        if validation["errors"] or validation["warnings"]:
            has_issues = True
            print(f"论文: {item['paper_id'][:60]}")
            coords = item.get("coordinates")
            if coords:
                print(f"  坐标: ({coords.get('latitude'):.2f}, {coords.get('longitude'):.2f})")

            if validation["errors"]:
                for err in validation["errors"]:
                    print(f"  ❌ {err}")

            if validation["warnings"]:
                for warn in validation["warnings"]:
                    print(f"  ⚠️  {warn}")

            if validation["suggestions"]:
                for sug in validation["suggestions"]:
                    if "✅" in sug:
                        print(f"  {sug}")
            print()

    if not has_issues:
        print("🎉 所有样本通过校验！")

    # 保存
    output_file = args.input_file.replace(".json", "_validation_v3.json")
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"详细报告: {output_file}")
