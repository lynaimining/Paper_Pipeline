#!/usr/bin/env python3
"""
Pipeline v4 对抗复核 + 元变换幻觉检测 (P2 + P7)
───────────────────────────────────────────────
P2 对抗复核：独立上下文审查 deposit_type 是否与原文一致
  - 输入原文前600字 + 提取结果
  - 输出 {consistent, issues, suggested_type, confidence}
  - 通过 → _provenance.deposit_type_verified = True
  - 不通过 → 进 review 桶，标记 FLAG:adversarial_fail

P7 元变换检测：摘要 vs 全文提取一致性（无需 ground truth）
  - 对 deposit_type != null 的论文：单独用摘要(前1500字)再跑一次提取
  - 比较摘要版 vs 全文版 deposit_type 是否同族
  - 不��致 → FLAG:metamorphic_inconsistency，进 review 桶

用法:
  export DEEPSEEK_API_KEY="sk-xxx"
  python adversarial_review.py <trusted.json> <corpus_root> <output_dir> [--max N] [--p2-only] [--p7-only]
"""
import os, sys, json, asyncio, argparse, hashlib
from pathlib import Path
from openai import AsyncOpenAI

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"

# ── P2 审查 prompt（完全独立上下文，不注入原始提取的推理过程）──
ADVERSARIAL_SYSTEM = "你是一位独立的矿床地质学专家审查员。你没有看到原始论文的任何分析过程。你的任务是独立判断一篇论文的提取结果是否与原文一致。"

ADVERSARIAL_USER = """请审查以下地质论文**引言和地质背景**部分（前3000字）与结构化提取结果的一致性。

论文ID: {paper_id}

论文引言/地质背景（原文前3000字）:
{head}

已提取结果:
- deposit_type: {deposit_type}
- deposit_type_evidence: {evidence}
- countries: {countries}
- metallogenic_belt: {belt}

请独立判断：
1. 论文引言是否支持 deposit_type={deposit_type}？
2. 有无明显错误或遗漏？
3. 是否应归为其他矿床类型？

只输出一个JSON:
{{"consistent": true/false, "confidence": 0.0-1.0, "issues": "发现的问题（无则null）", "suggested_type": "建议类型（与原结果一致则填原值）"}}"""

# ── P7 元变换提取 prompt（仅用摘要）──
METAMORPHIC_SYSTEM = "你是矿床地质学专家。仅根据论文前1500字判断矿床类型。"

METAMORPHIC_USER = """论文ID: {paper_id}

论文摘要（前1500字）:
{head}

仅根据以上内容判断矿床类型（从受控词表选最接近的，或null）。
受控词表: PORPHYRY-CU, PORPHYRY-CU-AU, PORPHYRY, EPITHERMAL-HS, EPITHERMAL-LS, EPITHERMAL-AU, EPITHERMAL, OROG-AU, CARLIN-AU, IOCG, SKARN-CU-AU, SKARN-PB-ZN, SKARN-FE, SKARN, VMS, SMS, SEDEX, MVT, NI-CU-PGE, NI-CU, PGE-REEF, PGE-CR, CARBONATITE-REE, CARBONATITE, PEGMATITE-LCT, PEGMATITE-NYF, PEGMATITE, U-SANDSTONE, U-UNCONFORMITY, LATERITE-REE, LATERITE-NI, KUPFERSCHIEFER, BIF-FE, BAUXITE, PHOSPHORITE, GREISEN-W-SN, GREISEN, VEIN-AU, VEIN-SN, KIMBERLITE, POLYMETALLIC

只输出JSON: {{"deposit_type": "类型或null", "confidence": 0.0-1.0, "reason": "一句话"}}"""


# ── 受控词表族群（同族=一致）──
FAMILY_MAP = {
    "PORPHYRY":    {"PORPHYRY", "PORPHYRY-SKARN", "PORPHYRY-CU", "PORPHYRY-CU-AU", "PORPHYRY-CU-MO",
                    "PORPHYRY-MO", "PORPHYRY-AU", "PORPHYRY-SN", "PORPHYRY-W",
                    "PORPHYRY-AU-CU", "PORPHYRY-SKARN"},
    "EPITHERMAL":  {"EPITHERMAL", "EPITHERMAL-HS", "EPITHERMAL-IS", "EPITHERMAL-LS",
                    "EPITHERMAL-AU", "EPITHERMAL-AG", "EPITHERMAL-AG-AU", "ALUNITE-AU"},
    "OROG-AU":     {"OROG-AU"},
    "PLACER-AU":   {"PLACER-AU", "PLACER-AU-PALEO", "OROG-AU-PALEO"},
    "SKARN":       {"SKARN", "SKARN-CU-AU", "SKARN-CU", "SKARN-PB-ZN", "SKARN-FE",
                    "SKARN-W", "SKARN-W-SN", "SKARN-SN", "SKARN-AU", "SKARN-MN", "SKARN-CU-FE"},
    "VMS":         {"VMS", "SMS"},
    "SEDEX":       {"SEDEX"},
    "MVT":         {"MVT", "IRISH-PB-ZN"},
    "IOCG":        {"IOCG", "KIRUNA-FE"},
    "NI-CU":       {"NI-CU", "NI-CU-PGE"},
    "PGE":         {"PGE-REEF", "PGE-CR", "CR-OPHIOLITE", "CR-STRATIFORM", "PLACER-PGE"},
    "CARBONATITE": {"CARBONATITE", "CARBONATITE-REE", "CARBONATITE-NB", "CARBONATITE-P",
                    "CARBONATITE-SKARN"},
    "PEGMATITE":   {"PEGMATITE", "PEGMATITE-LCT", "PEGMATITE-NYF", "PEGMATITE-REE"},
    "U":           {"U-SANDSTONE", "U-UNCONFORMITY", "U-ALBITITE", "U-VEIN", "U-PHOSPHATE"},
    "LATERITE":    {"LATERITE-NI", "LATERITE-REE", "LATERITE-AU", "NI-LATERITE", "RESIDUAL-MN"},
    "SEDIMENTARY": {"BIF-FE", "SEDIMENTARY-MN", "SEDIMENTARY-P", "EVAPORITE",
                    "COAL", "GRAPHITE", "BAUXITE"},
    "CU-SEDIMENT": {"KUPFERSCHIEFER", "SANDSTONE-CU", "SEDIMENT-CU"},
    "PLACER":      {"PLACER", "PLACER-TI-ZR", "PLACER-TIN"},
    "GREISEN":     {"GREISEN", "GREISEN-W-SN", "GREISEN-SN", "GREISEN-W"},
    "VEIN":        {"VEIN-AU", "VEIN-AG", "VEIN-CU", "VEIN-PB-ZN", "VEIN-SN-W",
                    "VEIN-SN", "FIVE-ELEMENT"},
    "DIAMOND":     {"KIMBERLITE", "LAMPROITE-DIAMOND"},
}

def same_family(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a, b = a.upper(), b.upper()
    if a == b:
        return True
    for members in FAMILY_MAP.values():
        if a in members and b in members:
            return True
    return False


def find_md(corpus_root: str, paper_id: str) -> str | None:
    """递归查找论文 MD 文件"""
    for p in Path(corpus_root).rglob(f"auto/{paper_id}.md"):
        return str(p)
    return None


def load_head(md_path: str, chars: int = 1500) -> str:
    text = open(md_path, encoding="utf-8").read()
    for marker in ["# References", "## References", "# REFERENCES"]:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]
    return text[:chars]


async def p2_review_one(client: AsyncOpenAI, item: dict, corpus_root: str,
                         semaphore: asyncio.Semaphore) -> dict:
    """P2: 单篇对抗复核"""
    paper_id = item.get("paper_id", "")
    rec = item.get("extracted") or item

    conf = float(rec.get('deposit_type_conf') or 0)
    if conf < 0.8:
        return {"paper_id": paper_id, "p2_result": None, "p2_skip": "low_confidence"}

    # P2 只对 mineral_deposit 类论文运行——方法学论文摘要里没有矿床证据
    dep_class = rec.get('deposit_class', '')
    if dep_class != 'mineral_deposit':
        return {"paper_id": paper_id, "p2_result": None, "p2_skip": f"class={dep_class}"}

    md_path = find_md(corpus_root, paper_id)
    if not md_path:
        return {"paper_id": paper_id, "p2_result": None, "p2_error": "md_not_found"}

    head = load_head(md_path, 3000)  # 引言+地质背景，3000字
    deposit_type = rec.get("deposit_type") or "null"
    evidence = (rec.get("deposit_type_evidence") or "")[:400]
    countries = rec.get("countries")
    belt = rec.get("metallogenic_belt")

    async with semaphore:
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": ADVERSARIAL_SYSTEM},
                    {"role": "user", "content": ADVERSARIAL_USER.format(
                        paper_id=paper_id, head=head,
                        deposit_type=deposit_type, evidence=evidence,
                        countries=countries, belt=belt,
                    )},
                ],
                temperature=0.0,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            result = json.loads(resp.choices[0].message.content)
            return {"paper_id": paper_id, "p2_result": result}
        except Exception as e:
            return {"paper_id": paper_id, "p2_result": None, "p2_error": str(e)}


async def p7_metamorphic_one(client: AsyncOpenAI, item: dict, corpus_root: str,
                              semaphore: asyncio.Semaphore) -> dict:
    """P7: 单篇元变换检测（摘要 vs 全文）"""
    paper_id = item.get("paper_id", "")
    rec = item.get("extracted") or item
    fulltext_type = rec.get("deposit_type")

    if not fulltext_type:
        return {"paper_id": paper_id, "p7_result": None, "p7_skip": "deposit_type_null"}

    md_path = find_md(corpus_root, paper_id)
    if not md_path:
        return {"paper_id": paper_id, "p7_result": None, "p7_error": "md_not_found"}

    head = load_head(md_path, 1500)

    async with semaphore:
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": METAMORPHIC_SYSTEM},
                    {"role": "user", "content": METAMORPHIC_USER.format(
                        paper_id=paper_id, head=head)},
                ],
                temperature=0.0,
                max_tokens=120,
                response_format={"type": "json_object"},
            )
            abstract_result = json.loads(resp.choices[0].message.content)
            abstract_type = abstract_result.get("deposit_type")
            consistent = same_family(fulltext_type, abstract_type)
            return {
                "paper_id": paper_id,
                "fulltext_type": fulltext_type,
                "abstract_type": abstract_type,
                "consistent": consistent,
                "p7_result": abstract_result,
            }
        except Exception as e:
            return {"paper_id": paper_id, "p7_result": None, "p7_error": str(e)}


async def run(trusted_file: str, corpus_root: str, output_dir: str,
              max_papers: int = 0, run_p2: bool = True, run_p7: bool = True,
              concurrency: int = 10):

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误: 请设置 DEEPSEEK_API_KEY", file=sys.stderr)
        sys.exit(1)

    client = AsyncOpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    semaphore = asyncio.Semaphore(concurrency)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    data = json.load(open(trusted_file))
    if max_papers > 0:
        data = data[:max_papers]

    # 只对 deposit_type != null 的论文做 P2/P7
    deposit_papers = [item for item in data
                      if (item.get("extracted") or item).get("deposit_type")]
    print(f"总论文: {len(data)}, 含 deposit_type: {len(deposit_papers)}")

    p2_results, p7_results = [], []

    if run_p2:
        print(f"\n[P2] 对抗复核: {len(deposit_papers)} 篇...")
        tasks = [p2_review_one(client, item, corpus_root, semaphore)
                 for item in deposit_papers]
        p2_results = await asyncio.gather(*tasks)
        p2_pass = sum(1 for r in p2_results if r.get("p2_result", {}) and r["p2_result"].get("consistent"))
        p2_fail = sum(1 for r in p2_results if r.get("p2_result", {}) and not r["p2_result"].get("consistent"))
        print(f"  P2 通过: {p2_pass}, 失败: {p2_fail}, 错误: {len(p2_results)-p2_pass-p2_fail}")

    if run_p7:
        print(f"\n[P7] 元变换检测: {len(deposit_papers)} 篇...")
        tasks = [p7_metamorphic_one(client, item, corpus_root, semaphore)
                 for item in deposit_papers]
        p7_results = await asyncio.gather(*tasks)
        p7_consistent = sum(1 for r in p7_results if r.get("consistent") is True)
        p7_inconsistent = sum(1 for r in p7_results if r.get("consistent") is False)
        print(f"  P7 一致: {p7_consistent}, 不一致: {p7_inconsistent}")

    # 合并结果，更新 _provenance 和 flags
    p2_map = {r["paper_id"]: r for r in p2_results}
    p7_map = {r["paper_id"]: r for r in p7_results}

    flagged = []
    for item in data:
        paper_id = item.get("paper_id", "")
        rec = item.get("extracted") or item
        flags = rec.get("_gate_flags") or []

        # P2 更新
        INSUFFICIENT_SUGGESTS = {None, 'None', 'UNKNOWN', 'unknown', '无法确定', '未指定', '', 'N/A', 'na'}
        p2r = p2_map.get(paper_id, {}).get("p2_result")
        if p2r:
            sug = p2r.get("suggested_type")
            is_insufficient = str(sug) in {str(x) for x in INSUFFICIENT_SUGGESTS}
            if p2r.get("consistent"):
                prov = rec.setdefault("_provenance", {})
                prov["deposit_type_verified"] = True
            elif is_insufficient:
                # 审查员无法从摘要确认，视为信息不足而非真正矛盾，标记但不入 flagged
                flags.append("FLAG:p2_insufficient_abstract")
            else:
                flags.append(f"FLAG:adversarial_fail:{p2r.get('issues','')[:80]}")
                if sug and sug != rec.get("deposit_type"):
                    flags.append(f"FLAG:p2_suggests:{sug}")
                flagged.append({"paper_id": paper_id, "reason": "p2_fail", "detail": p2r})

        # P7 更新
        p7r = p7_map.get(paper_id, {})
        if p7r.get("consistent") is False:
            flags.append(f"FLAG:metamorphic_inconsistency:{p7r.get('abstract_type')}")
            flagged.append({"paper_id": paper_id, "reason": "p7_inconsistent", "detail": p7r})

        if flags:
            rec["_gate_flags"] = flags

    # 写结果
    reviewed_file = out / "trusted_reviewed.json"
    json.dump(data, open(reviewed_file, "w"), ensure_ascii=False, indent=2)

    flagged_file = out / "adversarial_flagged.json"
    json.dump(flagged, open(flagged_file, "w"), ensure_ascii=False, indent=2)

    report = {
        "total": len(data),
        "deposit_papers": len(deposit_papers),
        "p2_pass": sum(1 for r in p2_results if r.get("p2_result", {}) and r["p2_result"].get("consistent")),
        "p2_fail": sum(1 for r in p2_results if r.get("p2_result", {}) and not r["p2_result"].get("consistent")),
        "p7_consistent": sum(1 for r in p7_results if r.get("consistent") is True),
        "p7_inconsistent": sum(1 for r in p7_results if r.get("consistent") is False),
        "total_flagged": len(flagged),
    }
    json.dump(report, open(out / "adversarial_report.json", "w"), ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"对抗复核 + 元变换检测完成")
    print(f"P2 verified: {report['p2_pass']}")
    print(f"P2 flagged:  {report['p2_fail']}")
    print(f"P7 consistent:    {report['p7_consistent']}")
    print(f"P7 inconsistent:  {report['p7_inconsistent']}")
    print(f"需人工复核: {report['total_flagged']} 篇")
    print(f"结果: {reviewed_file}")
    print(f"问题清单: {flagged_file}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("trusted_file", help="trusted.json 或 all_results.json")
    ap.add_argument("corpus_root", help="语料根目录")
    ap.add_argument("output_dir", help="输出目录")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--p2-only", action="store_true")
    ap.add_argument("--p7-only", action="store_true")
    ap.add_argument("--concurrency", type=int, default=10)
    args = ap.parse_args()
    asyncio.run(run(
        args.trusted_file, args.corpus_root, args.output_dir,
        max_papers=args.max,
        run_p2=not args.p7_only,
        run_p7=not args.p2_only,
        concurrency=args.concurrency,
    ))
