#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py — Paper Pipeline Final 主入口

支持三种起点：

  --mode pdf     : PDF 文件 → MinerU 解析 → 结构化抽取 → 全流程
  --mode corpus  : 已有 MinerU 产物目录 → 结构化抽取 → 全流程
  --mode trusted : 已有 trusted.json → 跳过 MinerU 和抽取 → 全流程

完整流程:
  Step 0  [pdf only]   magic-pdf 批量解析 PDF
  Step 1  [pdf/corpus] deepseek_extract.py  → extract_out/trusted.json
  Step 2               generate_qa.py       → _text_qa_all.jsonl
  Step 3  [可选]       qwen_vl_hf.py        → _qwen_out/qwen_vl_results.jsonl
  Step 4  [可选]       optimized_qa_pipeline → _image_qa_all.jsonl
  Step 5               process_paper.py     → unified/<paper_id>.jsonl  (并行)
  Step 6               build_global.py      → train/val/test.jsonl + stats

用法示例:

  # 从 PDF 目录开始（完整链路含图 QA）
  python run.py --mode pdf --input /data/pdfs \
      --output-dir dataset \
      --deepseek-key sk-xxx \
      --with-image-qa \
      --qwen-model /models/Qwen2.5-VL-7B-Instruct

  # 从 MinerU 产物目录开始（纯文本 QA）
  python run.py --mode corpus --input /data/mineru_output \
      --output-dir dataset \
      --deepseek-key sk-xxx

  # 从已有 trusted.json 开始（含图 QA，已有 Qwen 结果）
  python run.py --mode trusted --input extract_out/trusted.json \
      --output-dir dataset \
      --with-image-qa \
      --qwen-results /tmp/qwen_vl_results.jsonl

  # 只处理指定 paper_id
  python run.py --mode corpus --input /data/mineru_output \
      --paper-ids 2123 2143 2156 \
      --deepseek-key sk-xxx \
      --output-dir dataset
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent / "scripts"

# ── 固化超参 ──────────────────────────────────────────────────────────────────
QWEN_BATCH_DEFAULT = 4       # Blackwell 96GB: batch=4
WORKERS_DEFAULT    = 16      # process_paper CPU/IO 并行
CONCURRENCY_DEFAULT = 20     # DeepSeek API 并发


def run(cmd: list, desc: str = "") -> None:
    label = desc or " ".join(str(c) for c in cmd[:3])
    print(f"\n{'─'*60}\n▶  {label}\n{'─'*60}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n[FAIL] {label} exited {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


# ── Step 0: PDF → MinerU ──────────────────────────────────────────────────────

def step_pdf_to_mineru(pdf_dir: str, corpus_dir: str, workers: int) -> None:
    pdfs = sorted(glob.glob(os.path.join(pdf_dir, "**", "*.pdf"), recursive=True))
    if not pdfs:
        print(f"[WARN] 未找到 PDF: {pdf_dir}", file=sys.stderr)
        return

    Path(corpus_dir).mkdir(parents=True, exist_ok=True)
    print(f"[Step 0] 共 {len(pdfs)} 个 PDF，MinerU 解析 → {corpus_dir}")

    magic_cfg = Path(__file__).parent / "config" / "magic-pdf.json"
    if magic_cfg.exists():
        os.environ.setdefault("MAGIC_PDF_CONFIG_PATH", str(magic_cfg))

    def run_one(pdf_path):
        out_name = Path(pdf_path).stem
        cmd = [
            "magic-pdf", "-p", pdf_path,
            "-o", corpus_dir,
            "-m", "auto",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        ok = result.returncode == 0
        if not ok:
            print(f"  ✗ {out_name}: {result.stderr.strip()[:200]}", file=sys.stderr)
        return ok

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=1) as pool:  # MinerU 是 GPU 密集型，串行执行避免 OOM
        for success in pool.map(run_one, pdfs):
            if success:
                ok += 1
            else:
                fail += 1
    print(f"[Step 0] MinerU 完成: {ok} 成功 / {fail} 失败")


# ── Step 1: MinerU corpus → trusted.json ─────────────────────────────────────

def step_extract(corpus_dir: str, extract_out: str, concurrency: int,
                 deepseek_key: str | None) -> str:
    if deepseek_key:
        os.environ["DEEPSEEK_API_KEY"] = deepseek_key

    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("[ERROR] 需要 DEEPSEEK_API_KEY 环境变量或 --deepseek-key", file=sys.stderr)
        sys.exit(1)

    trusted_path = os.path.join(extract_out, "trusted.json")
    if Path(trusted_path).exists():
        print(f"[Step 1] 已有 trusted.json，跳过抽取: {trusted_path}")
        return trusted_path

    run([
        sys.executable, str(SCRIPTS_DIR / "deepseek_extract.py"),
        corpus_dir, extract_out,
        "--concurrency", str(concurrency),
    ], "deepseek_extract.py（结构化抽取）")
    return trusted_path


# ── Step 2: trusted.json → 文本 QA ────────────────────────────────────────────

def step_text_qa(trusted_json: str, output_dir: str) -> str:
    qa_path = os.path.join(output_dir, "_text_qa_all.jsonl")
    if Path(qa_path).exists():
        print(f"[Step 2] 已有文本 QA，跳过: {qa_path}")
        return qa_path
    run([
        sys.executable, str(SCRIPTS_DIR / "generate_qa.py"),
        trusted_json, "-o", qa_path, "--stats",
    ], "generate_qa.py（文本 QA 生成）")
    return qa_path


# ── Step 3: Qwen VL 推理 ───────────────────────────────────────────────────────

def step_qwen_vl(corpus_dir: str, qwen_out: str, qwen_model: str,
                 paper_ids: list, batch: int) -> str:
    results_path = os.path.join(qwen_out, "qwen_vl_results.jsonl")
    # 不在这里跳过——qwen_vl_hf.py 内部有 checkpoint 机制，会自动续跑未完成的图块

    Path(qwen_out).mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(SCRIPTS_DIR / "qwen_vl_hf.py"),
        "--corpus", corpus_dir,
        "--out", qwen_out,
        "--batch", str(batch),
    ]
    if qwen_model:
        cmd += ["--model", qwen_model]
    if paper_ids:
        # 写文件避免 shell 长参数和连字符 ID 问题
        papers_file = Path(qwen_out) / "_qwen_paper_ids.txt"
        papers_file.write_text("\n".join(paper_ids))
        cmd += ["--papers-file", str(papers_file)]

    run(cmd, "qwen_vl_hf.py（图像识别）")
    return results_path


# ── Step 4: 图 QA 生成 ────────────────────────────────────────────────────────

def step_image_qa(qwen_results: str, output_dir: str) -> tuple[str, str]:
    image_qa_path = os.path.join(output_dir, "_image_qa_all.jsonl")
    demoted_path  = os.path.join(output_dir, "_image_qa_text_demoted.jsonl")

    if Path(image_qa_path).exists():
        print(f"[Step 4] 已有图 QA，跳过: {image_qa_path}")
        return image_qa_path, demoted_path

    run([
        sys.executable, str(SCRIPTS_DIR / "optimized_qa_pipeline.py"),
        "--qwen-results", qwen_results,
        "--output", image_qa_path,
    ], "optimized_qa_pipeline.py（图 QA 生成）")
    return image_qa_path, demoted_path


# ── Step 5–6: per-paper + 全局聚合 ───────────────────────────────────────────

def step_pipeline_final(trusted_json: str, text_qa: str, output_dir: str,
                        paper_ids: list, eg_root: str, workers: int,
                        image_qa: str | None, demoted: str | None,
                        split_ratio: list, seed: int) -> None:

    # paper_id 可能含连字符开头（JAES 长文件名），直接放命令行会被 argparse 误解为 flag
    # 统一写文件传递，彻底规避这个问题
    if not paper_ids:
        paper_ids = [str(r["paper_id"]) for r in json.loads(Path(trusted_json).read_text())]
    ids_file = Path(output_dir) / "_paper_ids_for_pipeline.txt"
    ids_file.write_text("\n".join(paper_ids) + "\n")

    cmd = [
        sys.executable, str(SCRIPTS_DIR / "pipeline_final.py"),
        "--trusted-json", trusted_json,
        "--text-qa-jsonl", text_qa,
        "--output-dir", output_dir,
        "--workers", str(workers),
        "--split-ratio", str(split_ratio[0]), str(split_ratio[1]), str(split_ratio[2]),
        "--seed", str(seed),
        "--paper-ids-file", str(ids_file),
    ]
    if eg_root:
        cmd += ["--eg-root", eg_root]
    if image_qa and Path(image_qa).exists():
        cmd += ["--image-qa-out", image_qa]
        if demoted and Path(demoted).exists():
            cmd += ["--demoted-out", demoted]

    run(cmd, "pipeline_final.py（per-paper 处理 + 全局聚合）")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Paper Pipeline Final — 一键从 PDF/MinerU/trusted.json 产出 ShareGPT 数据集",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", choices=["pdf", "corpus", "trusted"], required=True,
                        help="起点模式: pdf=从原始PDF, corpus=从MinerU产物, trusted=从trusted.json")
    parser.add_argument("--input", required=True,
                        help="pdf模式: PDF目录; corpus模式: MinerU产物目录; trusted模式: trusted.json路径")
    parser.add_argument("--output-dir", default="dataset",
                        help="最终输出目录（默认: dataset）")
    parser.add_argument("--paper-ids", nargs="+", default=None,
                        help="只处理指定 paper_id（默认全部；含连字符开头的 ID 请用 --paper-ids-file）")
    parser.add_argument("--paper-ids-file", default=None,
                        help="每行一个 paper_id 的文件，规避 argparse 误解连字符 ID")

    # DeepSeek 抽取
    parser.add_argument("--deepseek-key", default=None,
                        help="DeepSeek API key（也可用 DEEPSEEK_API_KEY 环境变量）")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY_DEFAULT,
                        help=f"DeepSeek API 并发数（默认 {CONCURRENCY_DEFAULT}）")
    parser.add_argument("--extract-out", default=None,
                        help="deepseek_extract.py 输出目录（默认 <output-dir>/_extract）")

    # EG 根目录（用于查找 auto/）
    parser.add_argument("--eg-root", default="",
                        help="原始 PDF/auto 根目录，用于 symlink 图像（可选）")

    # 图 QA
    parser.add_argument("--with-image-qa", action="store_true",
                        help="启用图 QA（需要 GPU + Qwen VL）")
    parser.add_argument("--qwen-model", default="/root/autodl-tmp/models/qwen/Qwen2.5-VL-7B-Instruct",
                        help="Qwen VL 模型路径")
    parser.add_argument("--qwen-batch", type=int, default=QWEN_BATCH_DEFAULT,
                        help=f"Qwen VL batch 大小（默认 {QWEN_BATCH_DEFAULT}，Blackwell 96GB 最优）")
    parser.add_argument("--qwen-results", default=None,
                        help="已有的 qwen_vl_results.jsonl（跳过 Qwen 推理）")

    # process_paper 并行
    parser.add_argument("--workers", type=int, default=WORKERS_DEFAULT,
                        help=f"process_paper 并行 workers（默认 {WORKERS_DEFAULT}）")

    # 切分
    parser.add_argument("--split-ratio", nargs=3, type=float, default=[0.8, 0.1, 0.1],
                        metavar=("TRAIN", "VAL", "TEST"))
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    # --paper-ids-file 优先（规避连字符 ID 被 argparse 误解）
    if args.paper_ids_file:
        with open(args.paper_ids_file, encoding='utf-8') as _f:
            args.paper_ids = [l.strip() for l in _f if l.strip()]

    output_dir  = Path(args.output_dir)
    source_dir  = output_dir / "_source"           # Golden Layer 原始产物
    extract_out = Path(args.extract_out) if args.extract_out else source_dir / "_extract"
    source_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    corpus_dir   = None
    trusted_json = None

    # ── 确定 corpus_dir 和 trusted_json ──────────────────────────────────────

    if args.mode == "pdf":
        corpus_dir = str(output_dir / "_corpus")
        step_pdf_to_mineru(args.input, corpus_dir, args.workers)

    elif args.mode == "corpus":
        corpus_dir = args.input

    elif args.mode == "trusted":
        trusted_json = args.input
        if not Path(trusted_json).exists():
            print(f"[ERROR] trusted.json 不存在: {trusted_json}", file=sys.stderr)
            sys.exit(1)

    # --eg-root 未指定时自动推断：corpus/pdf 模式用语料目录，trusted 模式留空
    if not args.eg_root:
        if corpus_dir:
            args.eg_root = corpus_dir

    # ── Step 1: 结构化抽取（pdf / corpus 模式）──────────────────────────────

    if trusted_json is None:
        trusted_json = step_extract(
            corpus_dir, str(extract_out), args.concurrency, args.deepseek_key
        )

    if not Path(trusted_json).exists():
        print(f"[ERROR] trusted.json 不生成: {trusted_json}", file=sys.stderr)
        sys.exit(1)

    # ── Step 2: 文本 QA ──────────────────────────────────────────────────────

    text_qa = step_text_qa(trusted_json, str(source_dir))

    # ── Step 3–4: 图 QA（可选）──────────────────────────────────────────────

    image_qa_path = None
    demoted_path  = None

    if args.with_image_qa:
        qwen_out = str(output_dir / "_qwen_out")

        if args.qwen_results and Path(args.qwen_results).exists():
            qwen_results = args.qwen_results
            print(f"[Step 3] 使用已有 Qwen 结果: {qwen_results}")
        else:
            if not corpus_dir:
                # trusted 模式下没有 corpus_dir，要求提供 --qwen-results
                print("[ERROR] --mode trusted 下使用 --with-image-qa 必须同时提供 --qwen-results",
                      file=sys.stderr)
                sys.exit(1)
            qwen_results = step_qwen_vl(
                corpus_dir, qwen_out, args.qwen_model,
                args.paper_ids or [], args.qwen_batch,
            )

        image_qa_path, demoted_path = step_image_qa(qwen_results, str(source_dir))
    else:
        print("[Step 3-4] 跳过图 QA（未指定 --with-image-qa）")

    # ── Step 5–6: per-paper 处理 + 全局聚合 ──────────────────────────────────

    step_pipeline_final(
        trusted_json = trusted_json,
        text_qa      = text_qa,
        output_dir   = str(source_dir),
        paper_ids    = args.paper_ids or [],
        eg_root      = args.eg_root,
        workers      = args.workers,
        image_qa     = image_qa_path,
        demoted      = demoted_path,
        split_ratio  = args.split_ratio,
        seed         = args.seed,
    )

    # ── export: 生成下游消费层 ──────────────────────────────────────────────
    run([
        sys.executable, str(SCRIPTS_DIR / "export.py"),
        "--source-dir", str(source_dir),
        "--output-dir", str(output_dir),
        "--targets", "A", "B", "C", "D", "E",
    ], "export.py（生成 A_vlm_sft + B_structured_db）")

    # ── 完成 ─────────────────────────────────────────────────���─���──────────────
    print(f"\n{'='*60}")
    print(f"Pipeline 完成!")
    print(f"  _source/         — Golden Layer 原始产物")
    print(f"  A_vlm_sft/       — LLaMA-Factory 训练集（train/val/test.jsonl）")
    print(f"  B_structured_db/ — 矿床结构化数据库（deposits.jsonl / .csv）")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
