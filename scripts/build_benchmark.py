#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_benchmark.py — 生成 D_benchmark/

两个评测集，均只包含 splits.json 里的 test 论文：

  extraction_eval.jsonl  — 抽取评测：给定论文全文，对比抽取结果
                           指标：关键字段 F1（deposit_type / coordinates /
                                 commodities / metallogenic_belt / tectonic_setting）
  qa_eval.jsonl          — QA 评测：给定问题[+图]，对比模型答案
                           格式：自定义，含 answer 字段和 qa_type 区分

同时输出 eval_metrics.py — 独立可运行的评测脚本。

用法:
  python build_benchmark.py \\
      --source-dir dataset/_source \\
      --output-dir dataset
"""
import argparse
import json
from pathlib import Path


# ── 关键字段定义（抽取 F1 的评测维度）───────────────────────────────────��────
# 每个字段定义 match_type：
#   exact   — 字符串精确匹配（大小写不敏感）
#   present — 只评估「有/无」（null vs 非null），不比较值
#   coord   — 坐标：lat/lon 各自 ±0.5° 内算命中
#   list    — 列表：primary 字段取交集 / 总数 计 F1
EXTRACTION_KEY_FIELDS = {
    "deposit_type":      "exact",
    "deposit_class":     "exact",
    "commodities":       "list",       # 比较 primary 列表
    "coordinates":       "coord",
    "metallogenic_belt": "present",
    "tectonic_setting":  "present",
    "host_rocks":        "present",
    "alteration":        "present",
}


def load_body(md_path: str) -> str:
    text = Path(md_path).read_text(encoding="utf-8")
    for marker in ["# References", "# REFERENCES", "## References", "## REFERENCES"]:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]
            break
    return text.strip()


def _norm_coords_for_eval(coords) -> dict | None:
    """将 {latitude/longitude} 或 {lat/lon} 统一为 eval_metrics 期望的 {lat, lon}。"""
    if not isinstance(coords, dict):
        return coords
    lat = coords.get("lat") or coords.get("latitude")
    lon = coords.get("lon") or coords.get("longitude")
    if lat is None and lon is None:
        return coords  # 保留原样，避免破坏 present 检查
    return {"lat": lat, "lon": lon}


def build_extraction_record(paper_id: str, body: str, trusted: dict) -> dict:
    """单条抽取评测记录。"""
    ground_truth = {
        field: trusted.get(field)
        for field in EXTRACTION_KEY_FIELDS
    }
    # 归一化坐标 key，使 eval_metrics.py 的 match_coord 能正确取值
    if "coordinates" in ground_truth:
        ground_truth["coordinates"] = _norm_coords_for_eval(ground_truth["coordinates"])
    return {
        "id":           f"ext_eval_{paper_id}",
        "paper_id":     paper_id,
        "eval_type":    "extraction",
        "input_text":   body,
        "ground_truth": ground_truth,
        "eval_fields":  EXTRACTION_KEY_FIELDS,
        "model_output": None,
        "scores":       None,
    }


def build_qa_records(paper_id: str, unified_jsonl: Path, split: str) -> list:
    """从 unified/<paper_id>.jsonl 读 test split 记录，加 answer 字段。"""
    if not unified_jsonl.exists():
        return []
    records = []
    with open(unified_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            convs = rec.get("conversations", [])

            # 提取标准答案：最后一个 gpt turn
            gpt_turns = [c["value"] for c in convs if c.get("from") == "gpt"]
            if not gpt_turns:
                continue

            # 多轮图 QA：保留完整对话结构作为参考答案
            qa_type = rec.get("qa_type", "text")
            if qa_type == "image":
                # 多轮：[Q1, A1, Q2, A2, ...]
                qa_pairs = []
                human_turns = [c["value"] for c in convs if c.get("from") == "human"]
                for q, a in zip(human_turns, gpt_turns):
                    qa_pairs.append({"question": q, "answer": a})
                answer_ref = qa_pairs
            else:
                answer_ref = gpt_turns[-1]

            records.append({
                "id":           rec["id"],
                "paper_id":     paper_id,
                "eval_type":    "qa",
                "qa_type":      qa_type,
                "dimension":    rec.get("dimension", ""),
                "quality_score": rec.get("quality_score"),
                "images":       rec.get("images", []),
                "conversations": convs,   # 完整对话（含 system）
                "answer_ref":   answer_ref,  # 标准答案（评测脚本对比用）
                # 模型输出占位
                "model_output": None,
                "scores":       None,
            })
    return records


def write_eval_metrics(out_dir: Path) -> None:
    """写出独立可运行的 eval_metrics.py。"""
    code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_metrics.py — D_benchmark 评测脚本

用法:
  # 先把模型输出填入 extraction_eval.jsonl 的 model_output 字段，再运行：
  python eval_metrics.py --eval-dir D_benchmark --type extraction
  python eval_metrics.py --eval-dir D_benchmark --type qa --metric rouge
"""
import argparse
import json
import re
from pathlib import Path


# ── 抽取评测：关键字段 F1 ─────────────────────────────────────────────────────

def norm_str(s) -> str:
    if s is None:
        return ""
    return str(s).strip().upper()


def match_exact(pred, gold) -> float:
    if gold is None and pred is None:
        return 1.0
    if gold is None or pred is None:
        return 0.0
    return 1.0 if norm_str(pred) == norm_str(gold) else 0.0


def match_present(pred, gold) -> float:
    """只评估有/无，忽略具体值。"""
    pred_has = pred is not None and pred != "" and pred != []
    gold_has = gold is not None and gold != "" and gold != []
    return 1.0 if pred_has == gold_has else 0.0


def match_coord(pred, gold, tolerance: float = 0.5) -> float:
    """坐标：lat/lon 各自在 tolerance 度内算命中，两者都命中得 1.0。"""
    if gold is None and pred is None:
        return 1.0
    if gold is None or pred is None:
        return 0.0
    try:
        if isinstance(pred, str):
            nums = re.findall(r"[-+]?\\d+\\.?\\d*", pred)
            pred = {"lat": float(nums[0]), "lon": float(nums[1])} if len(nums) >= 2 else None
        if pred is None:
            return 0.0
        lat_ok = abs(float(pred.get("lat", 999)) - float(gold.get("lat", 0))) <= tolerance
        lon_ok = abs(float(pred.get("lon", 999)) - float(gold.get("lon", 0))) <= tolerance
        return 1.0 if (lat_ok and lon_ok) else 0.5 if (lat_ok or lon_ok) else 0.0
    except (TypeError, ValueError, IndexError):
        return 0.0


def match_list(pred, gold) -> float:
    """列表字段（commodities.primary）：token-level F1。"""
    def to_set(v):
        if v is None:
            return set()
        if isinstance(v, dict):
            v = v.get("primary") or []
        if isinstance(v, list):
            return {norm_str(x) for x in v if x}
        return {norm_str(v)} if v else set()

    p_set, g_set = to_set(pred), to_set(gold)
    if not p_set and not g_set:
        return 1.0
    if not p_set or not g_set:
        return 0.0
    tp = len(p_set & g_set)
    precision = tp / len(p_set)
    recall    = tp / len(g_set)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


MATCH_FN = {
    "exact":   match_exact,
    "present": match_present,
    "coord":   match_coord,
    "list":    match_list,
}


def eval_extraction(eval_dir: Path) -> None:
    path = eval_dir / "extraction_eval.jsonl"
    records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    filled = [r for r in records if r.get("model_output") is not None]
    if not filled:
        print("model_output 全为 null，请先填入模型预测结果。")
        return

    field_scores: dict[str, list] = {}
    for rec in filled:
        gt     = rec["ground_truth"]
        pred   = rec["model_output"] if isinstance(rec["model_output"], dict) else {}
        fields = rec.get("eval_fields", {})
        for field, mtype in fields.items():
            score = MATCH_FN.get(mtype, match_exact)(pred.get(field), gt.get(field))
            field_scores.setdefault(field, []).append(score)

    print(f"\\n抽取评测结果（{len(filled)} / {len(records)} 条有预测）")
    print(f"{'字段':<25} {'F1/命中率':>10} {'样本数':>8}")
    print("-" * 46)
    overall = []
    for field, scores in sorted(field_scores.items()):
        avg = sum(scores) / len(scores)
        overall.append(avg)
        print(f"  {field:<23} {avg:>10.3f} {len(scores):>8}")
    print("-" * 46)
    print(f"  {'宏平均':<23} {sum(overall)/len(overall):>10.3f}")


# ── QA 评测：ROUGE-L ──────────────────────────────────────────────────────────

def lcs_len(a: list, b: list) -> int:
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = dp[i-1][j-1] + 1 if a[i-1] == b[j-1] else max(dp[i-1][j], dp[i][j-1])
    return dp[m][n]


def rouge_l(pred: str, ref: str) -> float:
    if not pred or not ref:
        return 0.0
    p_tok = pred.lower().split()
    r_tok = ref.lower().split()
    lcs   = lcs_len(p_tok, r_tok)
    if lcs == 0:
        return 0.0
    prec = lcs / len(p_tok)
    rec  = lcs / len(r_tok)
    return 2 * prec * rec / (prec + rec)


def eval_qa(eval_dir: Path) -> None:
    path = eval_dir / "qa_eval.jsonl"
    records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    filled = [r for r in records if r.get("model_output") is not None]
    if not filled:
        print("model_output 全为 null，请先填入模型预测结果。")
        return

    by_type: dict[str, list] = {}
    for rec in filled:
        ref  = rec.get("answer_ref", "")
        pred = rec.get("model_output", "")
        if isinstance(ref, list):        # 多轮图 QA，取所有 answer 拼接
            ref = " ".join(p.get("answer", "") for p in ref)
        if not isinstance(pred, str):
            pred = json.dumps(pred, ensure_ascii=False)
        score = rouge_l(str(pred), str(ref))
        qa_type = rec.get("qa_type", "text")
        by_type.setdefault(qa_type, []).append(score)

    print(f"\\nQA 评测结果（ROUGE-L）— {len(filled)} / {len(records)} 条有预测")
    print(f"{'类型':<15} {'ROUGE-L':>10} {'样本数':>8}")
    print("-" * 36)
    all_scores = []
    for qa_type, scores in sorted(by_type.items()):
        avg = sum(scores) / len(scores)
        all_scores.extend(scores)
        print(f"  {qa_type:<13} {avg:>10.3f} {len(scores):>8}")
    print("-" * 36)
    print(f"  {'总体':<13} {sum(all_scores)/len(all_scores):>10.3f}")


# ── 主入口 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-dir", default="D_benchmark")
    parser.add_argument("--type", choices=["extraction", "qa", "all"], default="all")
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir)
    if args.type in ("extraction", "all"):
        eval_extraction(eval_dir)
    if args.type in ("qa", "all"):
        eval_qa(eval_dir)
'''
    (out_dir / "eval_metrics.py").write_text(code, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="生成 D_benchmark/")
    parser.add_argument("--source-dir", required=True, help="_source/ 目录")
    parser.add_argument("--output-dir", required=True, help="输出根目录")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    out_dir    = Path(args.output_dir) / "D_benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── splits.json ───────────────────────────────────────────────────────────
    splits_data = json.loads((source_dir / "splits.json").read_text())
    split_map: dict = splits_data.get("split_map", splits_data)
    test_ids = [pid for pid, s in split_map.items() if s == "test"]

    if not test_ids:
        print("[WARN] splits.json 里没有 test 论文，benchmark 为空")
        return

    # ── trusted.json（两处查找：_source/ 和 _source/_extract/）────────────────
    trusted_path = source_dir / "trusted.json"
    if not trusted_path.exists():
        trusted_path = source_dir / "_extract" / "trusted.json"
    if not trusted_path.exists():
        raise FileNotFoundError(
            f"trusted.json 不存在，已查找:\n"
            f"  {source_dir / 'trusted.json'}\n"
            f"  {source_dir / '_extract' / 'trusted.json'}"
        )
    trusted_list = json.loads(trusted_path.read_text())
    trusted_map  = {str(r["paper_id"]): r for r in trusted_list}

    text_dir    = source_dir / "text"
    unified_dir = source_dir / "unified"

    extraction_records = []
    qa_records         = []

    for paper_id in sorted(test_ids):
        trusted = trusted_map.get(paper_id)
        if trusted is None:
            continue

        # ── 抽取评测记录 ──────────────────────────────────────────────────────
        md_path = text_dir / f"{paper_id}.md"
        if md_path.exists():
            body = load_body(str(md_path))
            if body:
                extraction_records.append(
                    build_extraction_record(paper_id, body, trusted)
                )

        # ── QA 评测记录 ───────────────────────────────────────────────────────
        qa_records.extend(
            build_qa_records(paper_id, unified_dir / f"{paper_id}.jsonl", "test")
        )

    # ── 写文件 ────────────────────────────────────────────────────────────────
    ext_path = out_dir / "extraction_eval.jsonl"
    with open(ext_path, "w", encoding="utf-8") as f:
        for rec in extraction_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    qa_path = out_dir / "qa_eval.jsonl"
    with open(qa_path, "w", encoding="utf-8") as f:
        for rec in qa_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ── 冻结标记 ─────────────────────────────────────────────────────────────
    freeze = {
        "frozen": True,
        "test_paper_ids": test_ids,
        "note": "test_paper_ids 一旦确定不得修改，所有模型版本共用同一份评测集",
    }
    (out_dir / "FROZEN.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2)
    )

    # ── 写评测脚本 ────────────────────────────────────────────────────────────
    write_eval_metrics(out_dir)

    print(f"  D 完成 → {out_dir}")
    print(f"    extraction_eval.jsonl  {len(extraction_records)} 条（{len(test_ids)} 篇 test）")
    print(f"    qa_eval.jsonl          {len(qa_records)} 条")
    print(f"    FROZEN.json            冻结 {len(test_ids)} 篇 test paper_ids")
    print(f"    eval_metrics.py        独立评测脚本（ROUGE-L + 关键字段 F1）")


if __name__ == "__main__":
    main()
