#!/usr/bin/env python3
"""
图像空间推理分类器
只保留真正需要空间推理的图：geological map / cross-section / 地球物理图（含被动源地震）
显式排除：photomicrograph、table、bar/scatter、噪声

用途：被 optimized_qa_pipeline.py 和 quality_monitor.py 复用
"""
import re
import json
import os

# ==================== 空间推理白名单 ====================

GEO_MAP_KEYWORDS = {
    "geological map", "geologic map", "tectonic map", "exploration map",
    "alteration map", "resource map", "regional map", "distribution map",
    "sampling map", "location map", "geological_map", "structural map",
    "deposit map", "mineralization map",
}

CROSS_SECTION_KEYWORDS = {
    "cross-section", "cross section", "cross section map",
    "geological cross-section", "drill section", "vertical section",
    "profile", "schematic section", "stratigraphic column",
    "stratigraphic section",
}

# 地球物理图 —— 全保留（磁/重力/IP/电磁/放射性/地震，含主动源+被动源）
GEOPHYS_MAP_KEYWORDS = {
    # 磁法
    "magnetic map", "magnetics map", "aeromagnetic map", "total magnetic intensity",
    "tmi map", "magnetic anomaly", "rtp",
    # ��力
    "gravity map", "bouguer anomaly", "free-air anomaly", "gravity anomaly",
    "agg", "airborne gravity",
    # 电法
    "ip map", "induced polarization", "chargeability map", "resistivity map",
    "electromagnetic map", "em map", "conductivity",
    # 放射性
    "radiometric map", "radiometrics",
    # 地震（主动源）
    "seismic map", "reflection seismic", "seismic section", "seismic profile",
    "seismic line", "seismic survey",
    # 地震（被动源）—— 用户明确要求
    "passive seismic", "ambient noise", "receiver function", "seismic tomography",
    "velocity model", "shear wave", "vs model", "vp model", "tomographic",
    "moho", "lithospheric",
    # 综合
    "geophysical map", "geophysical survey", "potential field",
}

# 显式排除（即使有Caption也丢弃）
# 注意：用精确词组而非 "diagram" 单词，避免 "cross-section diagram" 等合法地质图被误杀
JUNK_FIGURE_TYPES = {
    "photomicrograph", "photomicrography", "microscope", "thin section",
    "table", "bar chart", "bar graph", "histogram", "scatter plot",
    "scatter diagram", "pie chart", "line chart", "calendar", "flowchart",
    "flow chart", "icon", "crossmark", "logo", "null", "pencil icon",
    "ternary diagram", "harker diagram", "spider diagram", "rose diagram",
    "ternary", "harker", "spider",
}


def classify_figure(figure_type: str, caption: str = "") -> str:
    """
    返回分类: 'geo_map' | 'cross_section' | 'geophys_map' | 'junk'

    策略：先尝试归入空间推理类别（白名单优先），再判断 junk。
    这样 "cross-section diagram" 能进入 cross_section，而非被 diagram 误杀。
    """
    ft = (figure_type or "").lower().strip()
    if isinstance(caption, list):
        caption = ' '.join(str(x) for x in caption)
    cap = (caption or "").lower()
    combined = ft + " " + cap

    # ① 先尝试正向分类（白名单优先于黑名单）
    for kw in GEO_MAP_KEYWORDS:
        if kw in combined:
            return "geo_map"

    for kw in CROSS_SECTION_KEYWORDS:
        if kw in combined:
            return "cross_section"

    for kw in GEOPHYS_MAP_KEYWORDS:
        if kw in combined:
            return "geophys_map"

    # ② 白名单未命中，再判断 junk
    for junk in JUNK_FIGURE_TYPES:
        if junk in ft:
            return "junk"

    return "junk"


def parse_qwen_output(output_str: str) -> dict:
    """解析Qwen VL的output字段（JSON字符串，可能带```json```包裹）"""
    if not output_str:
        return {}
    m = re.search(r'\{[\s\S]*\}', output_str)
    if not m:
        return {}
    try:
        return json.loads(m.group())
    except Exception:
        return {}


def load_qwen_spatial_images(qwen_results_path: str) -> tuple[list, dict]:
    """
    从Qwen结果中加载所有「空间推理图」（已过滤junk）

    返回: [{image_path, caption, figure_type, category, text_in_figure, legend, paper_id}]
    """
    images = []
    stats = {"geo_map": 0, "cross_section": 0, "geophys_map": 0, "junk": 0, "table_task": 0}

    if not os.path.exists(qwen_results_path):
        raise FileNotFoundError(f"Qwen结果文件不存在: {qwen_results_path}")

    with open(qwen_results_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                import sys
                print(f"  WARN: {qwen_results_path}:{lineno} JSON解析失败，跳过: {e}", file=sys.stderr)
                continue

            # table任务直接归为junk
            if rec.get("task") == "table":
                stats["table_task"] += 1
                continue

            output = parse_qwen_output(rec.get("output", ""))
            figure_type = output.get("figure_type") or ""
            caption = output.get("title_or_caption") or rec.get("img_caption") or ""

            category = classify_figure(figure_type, caption)
            stats[category] += 1

            if category == "junk":
                continue

            images.append({
                "image_path": rec.get("image_path", ""),
                "caption": caption,
                "figure_type": figure_type,
                "category": category,
                "text_in_figure": output.get("text_in_figure", []),
                "legend": output.get("legend", []),
                "paper_id": rec.get("paper_id", ""),
            })

    return images, stats


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python figure_classifier.py <qwen_vl_results.jsonl>", file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]

    images, stats = load_qwen_spatial_images(path)

    print("=" * 60)
    print("图像空间推理分类统计")
    print("=" * 60)
    print(f"\n保留（空间推理图）:")
    print(f"  geo_map      : {stats['geo_map']}")
    print(f"  cross_section: {stats['cross_section']}")
    print(f"  geophys_map  : {stats['geophys_map']}")
    print(f"  小计         : {len(images)}")
    print(f"\n丢弃:")
    print(f"  junk(图)     : {stats['junk']}")
    print(f"  table任务    : {stats['table_task']}")
    print(f"\n保留率: {len(images)}/{len(images)+stats['junk']+stats['table_task']}")
