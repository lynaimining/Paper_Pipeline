#!/usr/bin/env python3
"""
坐标一致性校验模块 V2 - 基于geopandas精确边界
覆盖全球所有国家，无需硬编码边界数据
"""
import json
from typing import Dict, List, Optional
from pathlib import Path

try:
    import geopandas as gpd
    from shapely.geometry import Point
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False
    print("⚠️  geopandas未安装，降级到简化模式")


class CoordinateValidator:
    """坐标校验器（支持全球所有国家）"""

    def __init__(self):
        self.world = None
        if GEOPANDAS_AVAILABLE:
            try:
                # 加载Natural Earth数据集（全球国家边界）
                self.world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
                print(f"✅ 加载 {len(self.world)} 个国家/地区边界数据")
            except Exception as e:
                print(f"⚠️  加载geopandas数据失败: {e}")
                self.world = None

    def point_in_country(self, lat: float, lon: float, country: str) -> tuple[bool, str]:
        """
        精确判断点是否在国家内

        Returns:
            (is_inside: bool, actual_country: str)
        """
        if not GEOPANDAS_AVAILABLE or self.world is None:
            return True, "无法验证"  # 降级模式：假定正确

        point = Point(lon, lat)  # 注意：shapely是(lon, lat)

        # 查找点所在的国家
        for idx, row in self.world.iterrows():
            if row.geometry.contains(point):
                actual_country = row['name']
                # 名称匹配（支持多种变体）
                if self._country_match(country, actual_country):
                    return True, actual_country
                else:
                    return False, actual_country

        # 点不在任何国家内（可能在海洋）
        return False, "未知位置（可能在海洋）"

    def _country_match(self, claimed: str, actual: str) -> bool:
        """国家名称匹配（支持别名）"""
        # 标准化
        claimed_lower = claimed.lower().strip()
        actual_lower = actual.lower().strip()

        if claimed_lower == actual_lower:
            return True

        # 常见别名映射
        aliases = {
            'usa': ['united states', 'united states of america'],
            'uk': ['united kingdom'],
            'dr congo': ['democratic republic of the congo', 'congo (kinshasa)'],
            'tanzania': ['united republic of tanzania'],
            'russia': ['russian federation'],
        }

        for key, values in aliases.items():
            if claimed_lower in values or claimed_lower == key:
                if actual_lower in values or actual_lower == key:
                    return True

        return False

    def validate_record(self, record: dict) -> dict:
        """
        校验单条记录

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
            errors.append(f"纬度超出范围: {lat}")

        if not (-180 <= lon <= 180):
            errors.append(f"经度超出范围: {lon}")

        # 2. 国家边界精确校验（使用geopandas）
        if countries and self.world is not None:
            for country in countries:
                is_inside, actual_country = self.point_in_country(lat, lon, country)

                if not is_inside:
                    if actual_country != "未知位置（可能在海洋）":
                        errors.append(
                            f"坐标({lat:.2f}, {lon:.2f})不在声称的国家'{country}'内，"
                            f"实际位置: {actual_country}"
                        )
                    else:
                        warnings.append(
                            f"坐标({lat:.2f}, {lon:.2f})未匹配到任何国家（可能在海洋或边界争议区）"
                        )
                else:
                    # 验证通过，记录实际国家名
                    if actual_country != "无法验证":
                        suggestions.append(f"✅ 坐标在{actual_country}境内，验证通过")

        # 3. 南北半球一致性
        hemisphere_keywords = {
            "Northern": "北",
            "Southern": "南",
            "North": "北",
            "South": "南"
        }

        for keyword, expected in hemisphere_keywords.items():
            text = f"{metallogenic_belt} {countries}"
            if keyword in text:
                if keyword in ["Northern", "North"] and lat < 0:
                    warnings.append(f"提到'{keyword}'（北），但纬度{lat}在南半球")
                elif keyword in ["Southern", "South"] and lat > 0:
                    warnings.append(f"提到'{keyword}'（南），但纬度{lat}在北半球")

        # 4. 置信度与精度匹配
        confidence = coords.get("confidence", 0)
        precision = coords.get("precision", "")

        if precision == "矿区级" and confidence < 0.8:
            warnings.append(f"矿区级精度但置信度偏低({confidence:.2f})")

        if precision == "省级" and confidence > 0.9:
            warnings.append(f"省级精度但置信度过高({confidence:.2f})，可能实际是矿区级")

        # 5. 建议
        if errors:
            suggestions.append("建议人工复核坐标")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "suggestions": suggestions
        }


def batch_validate(results: List[dict], validator: CoordinateValidator = None) -> dict:
    """批量校验"""

    if validator is None:
        validator = CoordinateValidator()

    validated = []
    stats = {
        "total": len(results),
        "valid": 0,
        "has_errors": 0,
        "has_warnings": 0
    }

    for record in results:
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

    if len(sys.argv) < 2:
        print("用法: python validate_coordinates_v2.py <results.json>")
        sys.exit(1)

    input_file = sys.argv[1]

    with open(input_file) as f:
        data = json.load(f)

    # 提取extracted字段
    if isinstance(data, list) and len(data) > 0 and "extracted" in data[0]:
        records = [r["extracted"] for r in data]
    else:
        records = data

    # 初始化校验器
    validator = CoordinateValidator()

    # 批量校验
    report = batch_validate(records, validator)

    # 打印报告
    print()
    print("=" * 80)
    print("坐标一致性校验报告 V2（基于geopandas精确边界）")
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

            print()

    if not has_issues:
        print("🎉 所有样本通过校验！")

    # 保存报告
    output_file = input_file.replace(".json", "_validation_v2.json")
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"详细报告已保存: {output_file}")
