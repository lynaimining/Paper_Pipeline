"""
Integration smoke test: generate_qa → process_paper → build_global
Uses 3 real records from trusted_100. No API, no GPU. Must run in <10s.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
CONFIG = Path(__file__).parent.parent / "config"
TRUSTED = CONFIG / "trusted_100_papers.json"


def _run(cmd, **kwargs):
    return subprocess.run(
        [sys.executable] + cmd,
        capture_output=True, text=True, encoding="utf-8",
        **kwargs
    )


@pytest.mark.skipif(not TRUSTED.exists(), reason="trusted_100 not available")
def test_full_pipeline_smoke(tmp_path):
    """generate_qa → process_paper → build_global: output structure is valid."""
    # Use 3 mineral deposit records
    records = json.loads(TRUSTED.read_text(encoding="utf-8"))
    mineral = [r for r in records if r.get("deposit_class") == "mineral_deposit"][:3]
    assert len(mineral) >= 3, "Need at least 3 mineral deposit records"

    mini_trusted = tmp_path / "mini_trusted.json"
    mini_trusted.write_text(json.dumps(mineral), encoding="utf-8")

    # Step 1: generate_qa
    text_qa = tmp_path / "text_qa.jsonl"
    r1 = _run([str(SCRIPTS / "generate_qa.py"), str(mini_trusted), "-o", str(text_qa)])
    assert r1.returncode == 0, f"generate_qa failed:\n{r1.stderr}"
    qa_lines = [l for l in text_qa.read_text().splitlines() if l.strip()]
    assert len(qa_lines) > 0, "generate_qa produced no output"

    # Validate QA record structure
    sample_qa = json.loads(qa_lines[0])
    assert "id" in sample_qa
    assert "paper_id" in sample_qa
    assert "question" in sample_qa
    assert "answer" in sample_qa

    # Step 2: process_paper for each paper
    dataset_dir = tmp_path / "dataset"
    for rec in mineral:
        pid = str(rec["paper_id"])
        r2 = _run([
            str(SCRIPTS / "process_paper.py"),
            "--paper-id", pid,
            "--trusted-json", str(mini_trusted),
            "--text-qa-jsonl", str(text_qa),
            "--output-dir", str(dataset_dir),
        ])
        assert r2.returncode == 0, f"process_paper failed for {pid}:\n{r2.stderr}"

    unified_dir = dataset_dir / "unified"
    assert unified_dir.exists(), "unified/ directory not created"
    unified_files = list(unified_dir.glob("*.jsonl"))
    assert len(unified_files) == 3, f"Expected 3 unified files, got {len(unified_files)}"

    # Step 3: build_global
    output_dir = tmp_path / "global"
    r3 = _run([
        str(SCRIPTS / "build_global.py"),
        "--dataset-dir", str(dataset_dir),
        "--output-dir", str(output_dir),
        "--split-ratio", "0.6", "0.2", "0.2",
        "--seed", "42",
    ])
    assert r3.returncode == 0, f"build_global failed:\n{r3.stderr}"

    # Validate outputs
    for fname in ["train.jsonl", "val.jsonl", "test.jsonl", "splits.json", "stats.json", "unified_all.jsonl"]:
        assert (output_dir / fname).exists(), f"Missing output: {fname}"

    # Validate splits.json structure
    splits = json.loads((output_dir / "splits.json").read_text())
    assert "paper_ids" in splits
    assert set(splits["paper_ids"].keys()) == {"train", "val", "test"}

    # Validate no paper appears in multiple splits
    all_pids = {s: set(splits["paper_ids"][s]) for s in ["train", "val", "test"]}
    assert not (all_pids["train"] & all_pids["test"]), "train/test leakage detected"
    assert not (all_pids["train"] & all_pids["val"]), "train/val leakage detected"

    # Validate QA record structure in train.jsonl
    train_lines = [l for l in (output_dir / "train.jsonl").read_text().splitlines() if l.strip()]
    if train_lines:
        rec = json.loads(train_lines[0])
        assert "conversations" in rec, "Missing conversations field"
        assert "split" in rec, "Missing split field"
        assert rec["split"] == "train"
