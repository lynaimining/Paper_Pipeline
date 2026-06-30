"""generate_qa.py 测试（对齐原版接口）"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import generate_qa

TRUSTED_PATH = Path(__file__).parent.parent / "config" / "trusted_100_papers.json"


def _records():
    if not TRUSTED_PATH.exists():
        return []
    return json.loads(TRUSTED_PATH.read_text(encoding="utf-8"))


def test_mineral_record_generates_qa():
    records = _records()
    mineral = [r for r in records if r.get("deposit_class") == "mineral_deposit"]
    assert mineral, "trusted_100 里应有矿床论文"
    qas = generate_qa.generate_qa_for_record(mineral[0])
    assert len(qas) > 0, "矿床论文应生成至少1条 QA"


def test_qa_have_required_fields():
    records = _records()
    if not records:
        return
    for r in records[:10]:
        for qa in generate_qa.generate_qa_for_record(r):
            assert "id" in qa
            assert "question" in qa
            assert "answer" in qa
            assert "dimension" in qa
            assert qa["answer"].strip() != ""


def test_questions_do_not_contain_paper_id():
    """question 文本里不应出现 paper_id，防止模型学 ID→答案映射。"""
    records = _records()
    if not records:
        return
    for r in records:
        pid = str(r.get("paper_id", ""))
        for qa in generate_qa.generate_qa_for_record(r):
            assert pid not in qa["question"], (
                f"question 含 paper_id '{pid}': {qa['question'][:80]}"
            )


def test_ids_are_unique_within_record():
    records = _records()
    if not records:
        return
    for r in records[:20]:
        qas = generate_qa.generate_qa_for_record(r)
        ids = [q["id"] for q in qas]
        assert len(ids) == len(set(ids)), f"paper {r.get('paper_id')} QA id 有重复"


def test_non_mineral_records_handled():
    records = _records()
    non_mineral = [r for r in records if r.get("deposit_class") != "mineral_deposit"]
    # 非矿床论文可能生成0条（字段不满足），不应崩溃
    for r in non_mineral[:5]:
        try:
            qas = generate_qa.generate_qa_for_record(r)
            assert isinstance(qas, list)
        except Exception as e:
            raise AssertionError(f"非矿床论文处理崩溃: {r.get('paper_id')}: {e}")


def test_cli_output(tmp_path):
    """CLI 端到端验证"""
    if not TRUSTED_PATH.exists():
        return
    out_file = tmp_path / "qa.jsonl"
    result = subprocess.run(
        [sys.executable,
         str(Path(__file__).parent.parent / "scripts" / "generate_qa.py"),
         str(TRUSTED_PATH), "-o", str(out_file), "--stats"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    lines = [l for l in out_file.read_text().splitlines() if l.strip()]
    assert len(lines) > 1000, f"100篇论文应生成 >1000 条 QA，实际 {len(lines)}"
    rec = json.loads(lines[0])
    assert "question" in rec and "answer" in rec


def test_gold_standard_total_qa():
    """100篇金标应生成足够多的 QA（原版质量验证）"""
    records = _records()
    if not records:
        return
    total = sum(len(generate_qa.generate_qa_for_record(r)) for r in records)
    assert total >= 2000, f"100篇应生成 >=2000 条 QA，实际 {total}（可能接口不兼容）"
