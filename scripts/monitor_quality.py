#!/usr/bin/env python3
"""
分批部署质量监控脚本
实时监控关键指标，早期发现质量问题
"""
import json
import sys
from pathlib import Path


class QualityMonitor:
    """质量监控器"""

    def __init__(self):
        self.thresholds = {
            "coordinates_min": 0.65,      # coordinates填充率≥65%
            "deposit_scale_min": 0.45,    # deposit_scale填充率≥45%
            "geochemistry_min": 0.85,     # geochemistry填充率≥85%
            "minerals_min": 0.95,         # minerals填充率≥95%
            "commodities_min": 0.95,      # commodities填充率≥95%
        }

        self.warnings = []
        self.errors = []

    def check_fill_rate(self, results, field_name, threshold):
        """检查填充率"""
        filled = sum(1 for r in results if (r.get('extracted') or r).get(field_name))
        rate = filled / len(results) if results else 0

        if rate < threshold:
            self.warnings.append(
                f"{field_name}填充率{rate*100:.1f}%过低（阈值{threshold*100:.0f}%）"
            )

        return rate

    def check_data_validity(self, results):
        """检查数据有效性"""
        for i, result in enumerate(results):
            r = result.get('extracted') or result

            # 检查coordinates范围
            coords = r.get('coordinates')
            if coords:
                lat = coords.get('latitude')
                lon = coords.get('longitude')

                if lat and (lat < -90 or lat > 90):
                    self.errors.append(f"样本{i}: 纬度超出范围 {lat}")

                if lon and (lon < -180 or lon > 180):
                    self.errors.append(f"样本{i}: 经度超出范围 {lon}")

            # 检查deposit_scale范围
            scale = r.get('deposit_scale')
            if scale:
                tonnage = scale.get('tonnage', {}).get('value') if scale.get('tonnage') else None
                if tonnage and (tonnage < 0 or tonnage > 100000):
                    self.warnings.append(f"样本{i}: tonnage异常 {tonnage}")

                grade = scale.get('grade') or {}
                if isinstance(grade, dict):
                    for metal, value in grade.items():
                        if isinstance(value, (int, float)):
                            if value < 0:
                                self.errors.append(f"样本{i}: {metal}品位为负 {value}")
                            if 'percent' in metal and value > 100:
                                self.errors.append(f"样本{i}: {metal}超过100% {value}")

    def monitor_batch(self, results, batch_id=None):
        """监控一批结果"""
        self.warnings = []
        self.errors = []

        print("=" * 80)
        if batch_id:
            print(f"批次 #{batch_id} 质量监控")
        else:
            print("质量监控报告")
        print("=" * 80)
        print()

        total = len(results)
        print(f"样本数: {total}篇")
        print()

        # 检查填充率
        print("【填充率检查】")
        print("-" * 80)

        coords_rate = self.check_fill_rate(results, 'coordinates', self.thresholds['coordinates_min'])
        scale_rate = self.check_fill_rate(results, 'deposit_scale', self.thresholds['deposit_scale_min'])
        geochem_rate = self.check_fill_rate(results, 'geochemistry', self.thresholds['geochemistry_min'])
        minerals_rate = self.check_fill_rate(results, 'minerals', self.thresholds['minerals_min'])
        commodities_rate = self.check_fill_rate(results, 'commodities', self.thresholds['commodities_min'])

        print(f"  coordinates:   {coords_rate*100:5.1f}% {'✅' if coords_rate >= self.thresholds['coordinates_min'] else '⚠️ '}")
        print(f"  deposit_scale: {scale_rate*100:5.1f}% {'✅' if scale_rate >= self.thresholds['deposit_scale_min'] else '⚠️ '}")
        print(f"  geochemistry:  {geochem_rate*100:5.1f}% {'✅' if geochem_rate >= self.thresholds['geochemistry_min'] else '⚠️ '}")
        print(f"  minerals:      {minerals_rate*100:5.1f}% {'✅' if minerals_rate >= self.thresholds['minerals_min'] else '⚠️ '}")
        print(f"  commodities:   {commodities_rate*100:5.1f}% {'✅' if commodities_rate >= self.thresholds['commodities_min'] else '⚠️ '}")
        print()

        # 检查数据有效性
        print("【数据有效性检查】")
        print("-" * 80)
        self.check_data_validity(results)

        if not self.errors and not self.warnings:
            print("  ✅ 无异常")
        else:
            if self.errors:
                print(f"  ❌ 错误: {len(self.errors)}个")
                for err in self.errors[:5]:
                    print(f"     {err}")
                if len(self.errors) > 5:
                    print(f"     ... 共{len(self.errors)}个错误")

            if self.warnings:
                print(f"  ⚠️  警告: {len(self.warnings)}个")
                for warn in self.warnings[:5]:
                    print(f"     {warn}")
                if len(self.warnings) > 5:
                    print(f"     ... 共{len(self.warnings)}个警告")

        print()

        # 决策
        print("【决策】")
        print("-" * 80)

        if self.errors:
            print("  🔴 STOP - 发现严重错误，需要修复")
            return "STOP"
        elif len(self.warnings) > len(results) * 0.2:  # 警告超过20%
            print("  🟡 CAUTION - 警告较多，建议检查")
            return "CAUTION"
        else:
            print("  🟢 CONTINUE - 质量良好，继续")
            return "CONTINUE"


def main():
    if len(sys.argv) < 2:
        print("用法: python monitor_quality.py <input.json> [batch_id]")
        sys.exit(1)

    input_file = sys.argv[1]
    batch_id = sys.argv[2] if len(sys.argv) > 2 else None

    # 读取
    with open(input_file) as f:
        data = json.load(f)

    # 监控
    monitor = QualityMonitor()
    decision = monitor.monitor_batch(data, batch_id)

    # 返回状态码
    if decision == "STOP":
        sys.exit(1)
    elif decision == "CAUTION":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
