#!/usr/bin/env python3
"""
P1-D: Canonical Gate 版本锁定
部署前校验，确保使用正确的gate版本
"""
import sys
from pathlib import Path


def verify_canonical_gate(gate_module_path=None):
    """
    验证 gate_lite.py 是否为 canonical 版本

    Canonical版本特征：
    - 有 VALID_DEPOSIT_CLASSES（开放deposit_class枚举）
    - 没有 VALID_DEPOSIT_TYPES（旧版闭合deposit_type枚举）

    Args:
        gate_module_path: gate_lite.py 文件路径 (optional, 默认从scripts/导入)

    Returns:
        bool: 是否为canonical版本

    Raises:
        RuntimeError: 如果版本不正确
    """
    # 动态导入gate_lite
    if gate_module_path:
        import importlib.util
        spec = importlib.util.spec_from_file_location("gate_lite", gate_module_path)
        gate_lite = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate_lite)
    else:
        # 从scripts目录导入
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import gate_lite

    # 检查1: 必须有 VALID_DEPOSIT_CLASSES
    if not hasattr(gate_lite, 'VALID_DEPOSIT_CLASSES'):
        raise RuntimeError(
            "❌ 错误的gate版本！\n"
            "   缺少 VALID_DEPOSIT_CLASSES\n"
            "   这是旧版gate或未正确配置的gate"
        )

    # 检查2: 不能有 VALID_DEPOSIT_TYPES（旧版枚举）
    if hasattr(gate_lite, 'VALID_DEPOSIT_TYPES'):
        raise RuntimeError(
            "❌ 检测到旧版gate！\n"
            "   存在 VALID_DEPOSIT_TYPES 闭合枚举\n"
            "   旧版会误杀 17 种新矿床类型（51.3%矿床论文）\n"
            "   请使用 canonical 版本（开放deposit_class枚举）"
        )

    # 检查3: VALID_DEPOSIT_CLASSES 应该是合理的枚举
    valid_classes = getattr(gate_lite, 'VALID_DEPOSIT_CLASSES', [])
    expected_classes = ["mineral_deposit", "structural_tectonic", "geochemical_petrology",
                       "methodological", "energy", "none"]

    if not all(c in valid_classes for c in expected_classes):
        raise RuntimeError(
            f"❌ VALID_DEPOSIT_CLASSES 内容异常！\n"
            f"   期望: {expected_classes}\n"
            f"   实际: {valid_classes}"
        )

    print("✅ Canonical gate 校验通过")
    print(f"   VALID_DEPOSIT_CLASSES: {valid_classes}")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="验证 gate_lite.py 版本")
    parser.add_argument("--gate-path", help="gate_lite.py 文件路径")
    args = parser.parse_args()

    try:
        verify_canonical_gate(args.gate_path)
        print("\n部署前校验通过，可以安全使用该gate版本")
    except RuntimeError as e:
        print(f"\n{e}")
        print("\n❌ 部署前校验失败，请修复gate版本后再部署")
        sys.exit(1)
