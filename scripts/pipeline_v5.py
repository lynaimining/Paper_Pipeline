#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline_v5.py — Pipeline v5 批量驱动（支持并行 per-paper 处理）

流程:
  1. generate_qa.py          → 全量文本 QA JSONL（一次性）
  2. [可选] qwen_vl_extract  → 每篇图 QA（需 GPU）
  3. [可选] optimized_qa_pipeline → 图 QA + blind-test
  4. process_paper.py        → 每篇 unified JSONL（fail-hard，可并行）

用法（文本 QA 模式，无需 GPU）:
  python pipeline_v5.py
      --paper-ids 2123 2143 2156 2182 2197
      --trusted-json test_output/trusted.json
      --eg-root "/root/autodl-tmp/corpus/Economic Geology"
      --output-dir dataset
      --workers 8

用法（全链路，含图 QA）:
  python pipeline_v5.py --paper-ids 2123 2143 ... --with-image-qa
      --qwen-results /tmp/qwen_vl_results.jsonl
"""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


EG_ROOT_DEFAULT = ""  # 已由 pipeline_final.py 取代；此脚本保留仅供参考，请使用 pipeline_final.py
PIPELINE_DIR = Path(__file__).parent
TRUSTED_JSON = PIPELINE_DIR.parent / "test_output" / "trusted.json"
DATASET_DIR = PIPELINE_DIR.parent / "dataset"


def find_auto_dir(paper_id: str, eg_root: str) -> Path | None:
    """在 eg_root 下递归找 <paper_id>/auto 目录。"""
    base = Path(eg_root)
    for candidate in base.rglob(f"{paper_id}/auto"):
        if candidate.is_dir():
            return candidate
    return None


def run_silent(cmd: list) -> tuple[int, str, str]:
    """运行子进程，返回 (returncode, stdout, stderr)。"""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def process_one_paper(
    pid: str,
    trusted_json: str,
    text_qa_path: str,
    output_dir: Path,
    eg_root: str,
    image_qa_path: str | None,
    demoted_path: str | None,
    proc_script: Path,
) -> dict:
    """
    处理单篇 paper，返回 {'pid': pid, 'ok': bool, 'index': dict | None, 'err': str}。
    此函数在线程池中运行，所有输出收集后统一打印。
    """
    auto_dir = find_auto_dir(pid, eg_root)

    cmd = [
        sys.executable, str(proc_script),
        "--paper-id", pid,
        "--trusted-json", trusted_json,
        "--text-qa-jsonl", text_qa_path,
        "--output-dir", str(output_dir),
    ]
    if auto_dir:
        cmd += ["--auto-dir", str(auto_dir)]
    if image_qa_path and Path(image_qa_path).exists():
        cmd += ["--image-qa-jsonl", image_qa_path]
    if demoted_path and Path(demoted_path).exists():
        cmd += ["--demoted-jsonl", demoted_path]

    rc, stdout, stderr = run_silent(cmd)

    if rc != 0:
        return {"pid": pid, "ok": False, "index": None,
                "err": stderr.strip() or f"exit {rc}", "auto_dir": str(auto_dir)}

    idx_path = output_dir / "index" / f"{pid}.json"
    index = json.loads(idx_path.read_text()) if idx_path.exists() else None
    return {"pid": pid, "ok": True, "index": index, "err": "",
            "auto_dir": str(auto_dir) if auto_dir else None}


def main():
    parser = argparse.ArgumentParser(description="Pipeline v5 批量驱动")
    parser.add_argument("--paper-ids", nargs="+", required=True)
    parser.add_argument("--trusted-json", default=str(TRUSTED_JSON))
    parser.add_argument("--eg-root", default=EG_ROOT_DEFAULT)
    parser.add_argument("--output-dir", default=str(DATASET_DIR))
    parser.add_argument("--workers", type=int, default=8,
                        help="per-paper 并行数（process_paper.py 纯 CPU/IO，8-16 合理）")
    parser.add_argument("--text-qa-jsonl", default=None)
    parser.add_argument("--with-image-qa", action="store_true")
    parser.add_argument("--qwen-results", default=None)
    parser.add_argument("--image-qa-out", default=None)
    parser.add_argument("--demoted-out", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    proc_script = PIPELINE_DIR / "process_paper.py"
    gen_qa_script = PIPELINE_DIR / "generate_qa.py"

    # ── Step 1: 生成全量文本 QA ────────────────────────────────────────────
    if args.text_qa_jsonl and Path(args.text_qa_jsonl).exists():
        text_qa_path = args.text_qa_jsonl
        print(f"[Step 1] 使用已有文本 QA: {text_qa_path}")
    else:
        text_qa_path = str(output_dir / "_text_qa_all.jsonl")
        print(f"[Step 1] 生成全量文本 QA → {text_qa_path}")
        rc, out, err = run_silent([sys.executable, str(gen_qa_script),
                                   args.trusted_json, "-o", text_qa_path, "--stats"])
        print(out.rstrip())
        if rc != 0:
            print(err.rstrip(), file=sys.stderr)
            sys.exit(1)

    # ── Step 2: 图 QA（可选）──────────────────────────────────────────────
    image_qa_path = args.image_qa_out
    demoted_path = args.demoted_out
    if args.with_image_qa:
        if not args.qwen_results:
            print("ERROR: --with-image-qa requires --qwen-results", file=sys.stderr)
            sys.exit(1)
        if not image_qa_path:
            image_qa_path = str(output_dir / "_image_qa_all.jsonl")
        if not demoted_path:
            demoted_path = image_qa_path.replace(".jsonl", "_text_demoted.jsonl")
        print(f"[Step 2] 生成图 QA → {image_qa_path}")
        rc, out, err = run_silent([
            sys.executable, str(PIPELINE_DIR / "optimized_qa_pipeline.py"),
            "--qwen-results", args.qwen_results, "--output", image_qa_path,
        ])
        print(out.rstrip())
        if rc != 0:
            print(err.rstrip(), file=sys.stderr)
            sys.exit(1)
    else:
        print("[Step 2] 跳过图 QA（未指定 --with-image-qa）")

    # ── Step 3: 并行处理每篇 ──────────────────────────────────────────────
    n = len(args.paper_ids)
    workers = min(args.workers, n)
    print(f"\n[Step 3] 处理 {n} 篇（{workers} workers 并行）")

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                process_one_paper,
                pid, args.trusted_json, text_qa_path, output_dir,
                args.eg_root, image_qa_path, demoted_path, proc_script,
            ): pid
            for pid in args.paper_ids
        }
        for fut in as_completed(futures):
            r = fut.result()
            status = "✓" if r["ok"] else "✗"
            auto_tag = f" [auto: {Path(r['auto_dir']).parent.name if r['auto_dir'] else 'none'}]"
            if r["ok"] and r["index"]:
                idx = r["index"]
                print(f"  {status} {r['pid']} | dep={idx.get('deposit_type','?')} "
                      f"qa={idx.get('n_total',0)} (txt={idx.get('n_text_qa',0)} img={idx.get('n_image_groups',0)})"
                      f"{auto_tag}")
            else:
                print(f"  {status} {r['pid']} FAIL: {r['err'][:120]}", file=sys.stderr)
            results.append(r)

    # ── Summary ────────────────────────────────────────────────────────────
    ok_results = [r for r in results if r["ok"]]
    failed = [r["pid"] for r in results if not r["ok"]]
    total_qa = sum(r["index"].get("n_total", 0) for r in ok_results if r["index"])
    total_txt = sum(r["index"].get("n_text_qa", 0) for r in ok_results if r["index"])
    total_img = sum(r["index"].get("n_image_groups", 0) for r in ok_results if r["index"])

    print(f"\n{'='*60}")
    print(f"完成: {len(ok_results)} / {n} 篇  QA: {total_qa} (文本 {total_txt} + 图组 {total_img})")
    if failed:
        print(f"失败 ({len(failed)}): {failed}", file=sys.stderr)
        sys.exit(1)
    print(f"输出: {output_dir}/unified/")


if __name__ == "__main__":
    main()
