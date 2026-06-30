"""build_global.py 测试"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "build_global.py"


def _run(dataset_dir, output_dir, ratio="0.8 0.1 0.1", seed=42):
    cmd = [
        sys.executable, str(SCRIPT),
        "--dataset-dir", str(dataset_dir),
        "--output-dir", str(output_dir),
        "--split-ratio", *ratio.split(),
        "--seed", str(seed),
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def _make_dataset(tmp_path, n_records=100):
    unified = tmp_path / "unified"
    unified.mkdir()
    records = [{"id": f"r{i}", "paper_id": str(i), "split": ""} for i in range(n_records)]
    with open(unified / "all.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return tmp_path


def test_split_totals_correct(tmp_path):
    _make_dataset(tmp_path, 100)
    result = _run(tmp_path, tmp_path)
    assert result.returncode == 0, result.stderr

    train = list(open(tmp_path / "train.jsonl"))
    val   = list(open(tmp_path / "val.jsonl"))
    test  = list(open(tmp_path / "test.jsonl"))
    assert len(train) + len(val) + len(test) == 100


def test_split_labels_correct(tmp_path):
    _make_dataset(tmp_path, 50)
    _run(tmp_path, tmp_path)

    for split in ["train", "val", "test"]:
        for line in open(tmp_path / f"{split}.jsonl"):
            rec = json.loads(line)
            assert rec["split"] == split


def test_seed_reproducibility(tmp_path):
    _make_dataset(tmp_path, 60)
    _run(tmp_path, tmp_path, seed=42)
    train1 = [json.loads(l)["id"] for l in open(tmp_path / "train.jsonl")]

    _run(tmp_path, tmp_path, seed=42)
    train2 = [json.loads(l)["id"] for l in open(tmp_path / "train.jsonl")]
    assert train1 == train2, "相同 seed 应产生相同顺序"


def test_different_seeds_differ(tmp_path):
    _make_dataset(tmp_path, 60)
    _run(tmp_path, tmp_path, seed=42)
    train1 = [json.loads(l)["id"] for l in open(tmp_path / "train.jsonl")]

    _run(tmp_path, tmp_path, seed=99)
    train2 = [json.loads(l)["id"] for l in open(tmp_path / "train.jsonl")]
    assert train1 != train2, "不同 seed 应产生不同顺序"


def test_invalid_ratio_exits_nonzero(tmp_path):
    _make_dataset(tmp_path, 10)
    result = _run(tmp_path, tmp_path, ratio="0.5 0.5 0.5")
    assert result.returncode != 0
    assert "1.0" in result.stderr or "1.0" in result.stdout


def test_no_unified_dir_exits_nonzero(tmp_path):
    result = _run(tmp_path, tmp_path)
    assert result.returncode != 0


def test_corrupt_jsonl_skipped(tmp_path):
    """单行坏 JSON 不应导致整体失败"""
    unified = tmp_path / "unified"
    unified.mkdir()
    with open(unified / "mixed.jsonl", "w") as f:
        f.write(json.dumps({"id": "ok1", "paper_id": "1"}) + "\n")
        f.write("{bad json\n")
        f.write(json.dumps({"id": "ok2", "paper_id": "2"}) + "\n")
    result = _run(tmp_path, tmp_path)
    assert result.returncode == 0
    total = sum(1 for s in ["train", "val", "test"]
                for _ in open(tmp_path / f"{s}.jsonl"))
    assert total == 2
