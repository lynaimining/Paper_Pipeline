#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline_final.py — Paper Pipeline Final 批量驱动（固化最优策略）

硬件基准（RTX PRO 6000 Blackwell 96 GB）：
  MinerU (GPU, formula/table off): 0.69 page/s
  Qwen2.5-VL-7B batch=4:          0.35 img/s  → ~36.6s/paper
  DeepSeek API concurrency=20:    ~1.7s/paper（抽取）

数据集输出：LLaMA-Factory ShareGPT 格式（conversations + images）

完整流程:
  Step 1  generate_qa        — 全量文本 QA
  Step 2  [可选] qwen_vl_hf  — Qwen VL 图像识别（需 GPU）
  Step 3  [可选] optimized_qa_pipeline — 图 QA 生成
  Step 4  process_paper      — per-paper unified jsonl（并行）
  Step 5  build_global       — 全局聚合 + train/val/test 切分

用法（纯文本模式）:
  python pipeline_final.py \\
      --paper-ids 2123 2143 2156 \\
      --trusted-json test_output/trusted_30.json \\
      --eg-root "/root/autodl-tmp/corpus/Economic Geology" \\
      --output-dir dataset_final

用法（含图 QA）:
  python pipeline_final.py \\
      --paper-ids 2123 2143 2156 \\
      --trusted-json test_output/trusted_30.json \\
      --eg-root "/root/autodl-tmp/corpus/Economic Geology" \\
      --output-dir dataset_final \\
      --with-image-qa \\
      --corpus /path/to/mineru/corpus
"""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


# ── 固化路径 ─────────────────────────────────────────────────────────────────
PIPELINE_DIR = Path(__file__).parent
EG_ROOT_DEFAULT = ""  # 必须由调用者通过 --eg-root 显式提供
QWEN_MODEL = "/root/autodl-tmp/models/qwen/Qwen2.5-VL-7B-Instruct"
TRUSTED_JSON_DEFAULT = PIPELINE_DIR.parent / "test_output" / "trusted_30.json"
DATASET_DIR_DEFAULT = PIPELINE_DIR.parent / "dataset_final"

# ── 固化最优超参 ─────────────────────────────────────────────────────────────
QWEN_BATCH = 4          # Blackwell 96GB 最优: batch=4 (core-saturated at batch=8)
PROCESS_WORKERS = 16    # process_paper 纯 CPU/IO，16 workers


def run_silent(cmd: list) -> tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def build_auto_dir_index(eg_root: str) -> dict:
    """一次性扫描 eg_root，建立 paper_id → auto_dir 映射，避免并发重复 rglob。"""
    if not eg_root or not Path(eg_root).exists():
        return {}
    index = {}
    for candidate in Path(eg_root).rglob("*/auto"):
        if candidate.is_dir():
            paper_id = candidate.parent.name
            if paper_id not in index:
                index[paper_id] = candidate
    return index


def process_one_paper(
    pid: str,
    trusted_json: str,
    text_qa_path: str,
    output_dir: Path,
    auto_dir_map: dict,
    image_qa_path: str | None,
    demoted_path: str | None,
    proc_script: Path,
) -> dict:
    auto_dir = auto_dir_map.get(pid)
    # 以连字符开头的 paper_id 用 --paper-id=<val> 形式，避免 argparse 误解为 flag
    pid_arg = f"--paper-id={pid}" if pid.startswith('-') else "--paper-id"
    cmd = [
        sys.executable, str(proc_script),
        pid_arg,
    ]
    if not pid.startswith('-'):
        cmd.append(pid)
    cmd += [
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
                "err": stderr.strip() or f"exit {rc}",
                "auto_dir": str(auto_dir) if auto_dir is not None else None}

    idx_path = output_dir / "index" / f"{pid}.json"
    index = json.loads(idx_path.read_text()) if idx_path.exists() else None
    return {"pid": pid, "ok": True, "index": index, "err": "",
            "auto_dir": str(auto_dir) if auto_dir else None}


def write_llamafactory_dataset_info(output_dir: Path) -> None:
    """
    在 output_dir 写 dataset_info.json（LLaMA-Factory 识别格式）。
    指向 train.jsonl / val.jsonl / test.jsonl。
    """
    info = {
        "geology_mineral_train": {
            "file_name": "train.jsonl",
            "formatting": "sharegpt",
            "columns": {"conversations": "conversations", "images": "images"},
        },
        "geology_mineral_val": {
            "file_name": "val.jsonl",
            "formatting": "sharegpt",
            "columns": {"conversations": "conversations", "images": "images"},
        },
        "geology_mineral_test": {
            "file_name": "test.jsonl",
            "formatting": "sharegpt",
            "columns": {"conversations": "conversations", "images": "images"},
        },
    }
    info_path = output_dir / "dataset_info.json"
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2))
    print(f"  dataset_info.json → {info_path}")


def main():
    parser = argparse.ArgumentParser(description="Paper Pipeline Final 批量驱动")
    parser.add_argument("--paper-ids", nargs="+", default=None, help="paper_id 列表（以 - 开头的 ID 请用 --paper-ids-file）")
    parser.add_argument("--paper-ids-file", default=None, help="每行一个 paper_id 的文件，规避 argparse 误解连字符 ID")
    parser.add_argument("--trusted-json", default=str(TRUSTED_JSON_DEFAULT))
    parser.add_argument("--eg-root", default=EG_ROOT_DEFAULT)
    parser.add_argument("--output-dir", default=str(DATASET_DIR_DEFAULT))
    parser.add_argument("--workers", type=int, default=PROCESS_WORKERS,
                        help=f"process_paper 并行数 (默认 {PROCESS_WORKERS})")
    # 文本 QA 选项
    parser.add_argument("--text-qa-jsonl", default=None,
                        help="已有的文本 QA JSONL（跳过 Step 1）")
    # 图 QA 选项
    parser.add_argument("--with-image-qa", action="store_true",
                        help="启用 Qwen VL 图像识别（需 GPU）")
    parser.add_argument("--corpus", default=None,
                        help="MinerU 处理后的语料库根目录（--with-image-qa 时必须）")
    parser.add_argument("--qwen-results", default=None,
                        help="已有的 qwen_vl_results.jsonl（跳过 Qwen 推理）")
    parser.add_argument("--image-qa-out", default=None)
    parser.add_argument("--demoted-out", default=None)
    # 切分
    parser.add_argument("--split-ratio", nargs=3, type=float, default=[0.8, 0.1, 0.1],
                        metavar=("TRAIN", "VAL", "TEST"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # --paper-ids-file 优先；否则用 --paper-ids；两者都没有则报错
    if args.paper_ids_file:
        with open(args.paper_ids_file, encoding='utf-8') as _f:
            args.paper_ids = [l.strip() for l in _f if l.strip()]
    elif not args.paper_ids:
        parser.error("必须提供 --paper-ids 或 --paper-ids-file")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    proc_script = PIPELINE_DIR / "process_paper.py"
    gen_qa_script = PIPELINE_DIR / "generate_qa.py"

    # ── Step 1: 文本 QA ──────────────────────────────────────────────────────
    if args.text_qa_jsonl and Path(args.text_qa_jsonl).exists():
        text_qa_path = args.text_qa_jsonl
        print(f"[Step 1] 使用已有文本 QA: {text_qa_path}")
    else:
        text_qa_path = str(output_dir / "_text_qa_all.jsonl")
        print(f"[Step 1] 生成全量文本 QA → {text_qa_path}")
        rc, out, err = run_silent([
            sys.executable, str(gen_qa_script),
            args.trusted_json, "-o", text_qa_path, "--stats",
        ])
        print(out.rstrip())
        if rc != 0:
            print(err.rstrip(), file=sys.stderr)
            sys.exit(1)

    # ── Step 2-3: 图 QA（可选）───────────────────────────────────────────────
    image_qa_path = args.image_qa_out
    demoted_path = args.demoted_out

    if args.with_image_qa:
        if not args.corpus and not args.qwen_results:
            print("ERROR: --with-image-qa requires --corpus or --qwen-results", file=sys.stderr)
            sys.exit(1)

        qwen_out_dir = str(output_dir / "_qwen_out")
        qwen_results_path = args.qwen_results

        if not qwen_results_path:
            qwen_results_path = str(Path(qwen_out_dir) / "qwen_vl_results.jsonl")
            print(f"[Step 2] Qwen VL 推理 (batch={QWEN_BATCH}) → {qwen_results_path}")
            rc, out, err = run_silent([
                sys.executable, str(PIPELINE_DIR / "qwen_vl_hf.py"),
                "--corpus", args.corpus,
                "--out", qwen_out_dir,
                "--batch", str(QWEN_BATCH),
                "--papers", ",".join(args.paper_ids),
            ])
            print(out.rstrip())
            if rc != 0:
                print(err.rstrip(), file=sys.stderr)
                sys.exit(1)
        else:
            print(f"[Step 2] 使用已有 Qwen VL 结果: {qwen_results_path}")

        if not image_qa_path:
            image_qa_path = str(output_dir / "_image_qa_all.jsonl")
        if not demoted_path:
            demoted_path = image_qa_path.replace(".jsonl", "_text_demoted.jsonl")

        if image_qa_path and Path(image_qa_path).exists():
            print(f"[Step 3] 使用已有图 QA: {image_qa_path} ({sum(1 for _ in open(image_qa_path))} 条)")
        else:
            print(f"[Step 3] 生成图 QA → {image_qa_path}")
            rc, out, err = run_silent([
                sys.executable, str(PIPELINE_DIR / "optimized_qa_pipeline.py"),
                "--qwen-results", qwen_results_path,
                "--output", image_qa_path,
            ])
            print(out.rstrip())
            if rc != 0:
                print(err.rstrip(), file=sys.stderr)
                sys.exit(1)
    else:
        print("[Step 2-3] 跳过图 QA（未指定 --with-image-qa）")

    # ── Step 4: 并行 per-paper 处理 ──────────────────────────────────────────
    n = len(args.paper_ids)
    workers = min(args.workers, n)
    print(f"\n[Step 4] 处理 {n} 篇（{workers} workers 并行）")

    # 预建 auto_dir 索引（一次扫描，避免 N 个 worker 各自 rglob）
    print(f"  构建 auto_dir 索引: {args.eg_root or '(未指定 eg_root，跳过)'}")
    auto_dir_map = build_auto_dir_index(args.eg_root)
    if args.eg_root:
        print(f"  索引完成: {len(auto_dir_map)} 个 auto 目录")

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                process_one_paper,
                pid, args.trusted_json, text_qa_path, output_dir,
                auto_dir_map, image_qa_path, demoted_path, proc_script,
            ): pid
            for pid in args.paper_ids
        }
        for fut in as_completed(futures):
            r = fut.result()
            status = "✓" if r["ok"] else "✗"
            if r["ok"] and r["index"]:
                idx = r["index"]
                auto_tag = f" [auto: {Path(r['auto_dir']).parent.name}]" if r["auto_dir"] is not None else ""
                print(f"  {status} {r['pid']} | dep={idx.get('deposit_type','?')} "
                      f"qa={idx.get('n_total',0)} "
                      f"(txt={idx.get('n_text_qa',0)} img={idx.get('n_image_groups',0)})"
                      f"{auto_tag}")
            else:
                print(f"  {status} {r['pid']} FAIL: {r['err'][:120]}", file=sys.stderr)
            results.append(r)

    failed = [r for r in results if not r["ok"]]
    if failed:
        print(f"\nWARNING: {len(failed)} 篇处理失败", file=sys.stderr)

    # ── Step 5: 全局聚合 + 切分 ───────────────────────────────────────────────
    print(f"\n[Step 5] 全局聚合 + train/val/test 切分")
    rc, out, err = run_silent([
        sys.executable, str(PIPELINE_DIR / "build_global.py"),
        "--dataset-dir", str(output_dir),
        "--output-dir", str(output_dir),
        "--split-ratio", str(args.split_ratio[0]),
                         str(args.split_ratio[1]),
                         str(args.split_ratio[2]),
        "--seed", str(args.seed),
    ])
    print(out.rstrip())
    if rc != 0:
        print(err.rstrip(), file=sys.stderr)
        sys.exit(1)

    # ── dataset_info.json（LLaMA-Factory 注册）────────────────────────────────
    write_llamafactory_dataset_info(output_dir)

    ok_count = sum(1 for r in results if r["ok"])

    # ── manifest.json ────────────────────────────────────────────────────────
    manifest = {
        "pipeline_version": "final-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "paper_count": {"total": n, "ok": ok_count, "failed": len(failed)},
        "config": {
            "trusted_json": args.trusted_json,
            "eg_root": args.eg_root,
            "workers": args.workers,
            "with_image_qa": args.with_image_qa,
            "split_ratio": args.split_ratio,
            "seed": args.seed,
        },
        "output_dir": str(output_dir),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"  manifest → {manifest_path}")

    print(f"\nDone: {ok_count}/{n} 篇成功 → {output_dir}")
    if failed:
        print(f"WARNING: {len(failed)} 篇因 auto_dir 缺失等原因跳过，不影响已成功篇的产出", file=sys.stderr)


if __name__ == "__main__":
    main()
