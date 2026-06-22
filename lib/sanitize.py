#!/usr/bin/env python3
"""
P1-E: 路径消毒模块
防止路径穿越和非法文件名
"""
import re
from pathlib import Path


def sanitize_paper_id(paper_id):
    """
    消毒 paper_id 用于文件路径

    Args:
        paper_id: 原始 paper_id

    Returns:
        消毒后的安全文件名
    """
    if not paper_id:
        return "unknown"

    # 移除路径穿越字符
    sanitized = paper_id.replace("../", "").replace("..\\", "")
    sanitized = sanitized.replace("/", "_").replace("\\", "_")
    sanitized = sanitized.replace("\x00", "")

    # Windows保留名前缀化
    reserved = ["CON", "PRN", "AUX", "NUL",
                "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"]

    name_upper = sanitized.upper().split('.')[0]  # 取文件名部分（不含扩展名）
    if name_upper in reserved:
        sanitized = f"file_{sanitized}"

    # 只保留安全字符：字母、数字、_、-、.、空格
    sanitized = re.sub(r'[^a-zA-Z0-9_\-\. ]', '_', sanitized)

    # 限制长度（文件系统通常限制255字符）
    if len(sanitized) > 200:
        sanitized = sanitized[:200]

    return sanitized


def safe_write_path(output_dir, paper_id, extension=".json"):
    """
    生成安全的写入路径，并验证不会写出目录外

    Args:
        output_dir: 输出目录
        paper_id: 论文ID
        extension: 文件扩展名

    Returns:
        Path对象，绝对路径

    Raises:
        ValueError: 如果路径会写出output_dir外
    """
    output_dir = Path(output_dir).resolve()

    # 消毒文件名
    safe_name = sanitize_paper_id(paper_id)
    if not safe_name.endswith(extension):
        safe_name = safe_name + extension

    # 构建路径
    target_path = (output_dir / safe_name).resolve()

    # 验证在目录内
    try:
        target_path.relative_to(output_dir)
    except ValueError:
        raise ValueError(f"路径穿越风险: {target_path} 不在 {output_dir} 内")

    return target_path


if __name__ == "__main__":
    # 测试
    test_cases = [
        "normal_paper",
        "paper with spaces",
        "paper/with/slashes",
        "paper\\with\\backslashes",
        "../../../etc/passwd",
        "CON",
        "LPT1.txt",
        "paper\x00null",
        "paper(1)",
    ]

    print("路径消毒测试:")
    for test in test_cases:
        safe = sanitize_paper_id(test)
        print(f"  {test:40} → {safe}")
