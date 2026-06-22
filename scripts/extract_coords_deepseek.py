#!/usr/bin/env python3
"""
针对性坐标提取：对有MD文件但缺坐标的论文，用DeepSeek专门提取坐标
"""
import os, sys, json, asyncio
from pathlib import Path
from openai import AsyncOpenAI

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

COORD_PROMPT = """从以下地质论文中提取研究区/主要矿床的地理坐标。

论文内容（前4000���）:
{text}

请仔细查找：
1. 明确给出的经纬度数字（如 32°N, 54°E 或 32.5°N, 54.2°E）
2. 地图图注中的坐标范围（取中心点）
3. 文字描述的位置（如 "位于X市以北50km" → 可推算）

若找到坐标，输出JSON:
{{"found": true, "latitude": 数字, "longitude": 数字, "precision": "矿床级/矿区级/地区级", "source": "引用的原文片段（≤50字）", "confidence": 0.6-1.0}}

若找不到任何坐标信息：
{{"found": false}}

只输出JSON，不要其他文字。"""


async def extract_coord(client, paper_id, md_path):
    text = open(md_path, encoding="utf-8", errors="ignore").read()[:4000]
    prompt = COORD_PROMPT.format(text=text)
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content.strip()
        # 提取JSON
        import re
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            result = json.loads(m.group())
            if result.get("found") and result.get("latitude") and result.get("longitude"):
                return paper_id, {
                    "latitude": float(result["latitude"]),
                    "longitude": float(result["longitude"]),
                    "precision": result.get("precision", "地区级"),
                    "source": result.get("source", "DeepSeek从文本提取"),
                    "confidence": float(result.get("confidence", 0.7)),
                    "extraction_method": "DeepSeek坐标专项提取",
                }
    except Exception as e:
        print(f"  {paper_id}: 失败 {e}", file=sys.stderr)
    return paper_id, None


async def main():
    if len(sys.argv) < 2:
        print("用法: python extract_coords_deepseek.py <input.json> [output.json]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace(".json", "_with_ds.json")

    with open(input_file) as f:
        data = json.load(f)

    # 找有MD文件但无坐标的记录
    md_dirs = [
        "/root/autodl-tmp/output/enhanced_md/Natural_Resources_Research_2016",
        "/root/autodl-tmp/output/enhanced_md/Natural_Resources_Research_2024",
        "/root/autodl-tmp/enhanced_md_2024",
    ]
    all_mds = {}
    for dd in md_dirs:
        if os.path.exists(dd):
            for f in os.listdir(dd):
                if f.endswith(".md"):
                    all_mds[f.replace(".md", "")] = os.path.join(dd, f)

    targets = []
    for r in data:
        rec = r.get("extracted") or r
        pid = rec.get("paper_id", "")
        if not rec.get("coordinates") and pid in all_mds:
            targets.append((pid, all_mds[pid], r))

    print(f"待提取: {len(targets)}篇")
    if not targets:
        print("无需处理")
        return

    client = AsyncOpenAI(api_key=API_KEY, base_url=DEEPSEEK_BASE_URL)

    # 并发提取（最多10并发）
    sem = asyncio.Semaphore(10)

    async def bounded(pid, path):
        async with sem:
            return await extract_coord(client, pid, path)

    tasks = [bounded(pid, path) for pid, path, _ in targets]
    results = await asyncio.gather(*tasks)

    coord_map = {pid: coord for pid, coord in results if coord}
    print(f"成功提取坐标: {len(coord_map)}篇")

    # 写回数据
    matched = 0
    for r in data:
        rec = r.get("extracted") or r
        pid = rec.get("paper_id", "")
        if pid in coord_map:
            rec["coordinates"] = coord_map[pid]
            matched += 1

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    total = len(data)
    after = sum(1 for r in data if (r.get("extracted") or r).get("coordinates"))
    print(f"新增: {matched} | 现有: {after}/{total} ({after/total*100:.1f}%)")
    print(f"输出: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
