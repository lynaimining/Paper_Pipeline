"""gate_lite.py 全量测试"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from gate_lite import gate_check, _DEPOSIT_TYPE_ALIASES


# ── helpers ──────────────────────────────────────────────────────────────────

def _run(records, dedup=False):
    results, report = gate_check(records, dedup=dedup)
    return results, report


def _flags(records, dedup=False):
    results, _ = _run(records, dedup=dedup)
    return [r["_gate_flags"] for r in results]


# ── P0: 主键 ─────────────────────────────────────────────────────────────────

def test_no_paper_id_fails():
    results, _ = _run([{"deposit_type": "OROG-AU"}])
    assert results[0]["_gate_status"] == "fail"
    assert any("no_paper_id" in f for f in results[0]["_gate_flags"])


def test_empty_paper_id_fails():
    results, _ = _run([{"paper_id": "  "}])
    assert results[0]["_gate_status"] == "fail"


def test_valid_paper_id_passes():
    results, _ = _run([{"paper_id": "123"}])
    assert results[0]["_gate_status"] == "pass"


# ── 坐标 ─────────────────────────────────────────────────────────────────────

def test_lat_zero_is_valid():
    """赤道 lat=0.0 不能被 or 短路丢弃"""
    results, _ = _run([{"paper_id": "1", "coordinates": {"lat": 0.0, "lon": 35.5}}])
    flags = results[0]["_gate_flags"]
    assert not any("lat" in f for f in flags), f"lat=0.0 不应有 flag: {flags}"


def test_lon_zero_is_valid():
    """本初子午线 lon=0.0 不能被 or 短路丢弃"""
    results, _ = _run([{"paper_id": "1", "coordinates": {"lat": 51.5, "lon": 0.0}}])
    flags = results[0]["_gate_flags"]
    assert not any("lon" in f for f in flags), f"lon=0.0 不应有 flag: {flags}"


def test_lat_out_of_range_fails():
    results, _ = _run([{"paper_id": "1", "coordinates": {"lat": 91.0, "lon": 0.0}}])
    assert any("FAIL:lat_out_of_range" in f for f in results[0]["_gate_flags"])


def test_lon_out_of_range_fails():
    results, _ = _run([{"paper_id": "1", "coordinates": {"lat": 0.0, "lon": 181.0}}])
    assert any("FAIL:lon_out_of_range" in f for f in results[0]["_gate_flags"])


def test_latitude_alias_key():
    """coords 用 'latitude'/'longitude' 长键也能正确读取"""
    results, _ = _run([{"paper_id": "1", "coordinates": {"latitude": 0.0, "longitude": 0.0}}])
    flags = results[0]["_gate_flags"]
    assert not any("FAIL" in f for f in flags)


# ── age 循环 ─────────────────────────────────────────────────────────────────

def test_age_all_bad_values_flagged():
    """修复前 break 导致第二个坏 age 被跳过"""
    results, _ = _run([{"paper_id": "1", "deposit_type": "OROG-AU",
                         "ages": [{"age_ma": -1}, {"age_ma": 9999}]}])
    flags = results[0]["_gate_flags"]
    age_flags = [f for f in flags if "age_out_of_range" in f]
    assert len(age_flags) == 2, f"期待2个age flag，得到: {age_flags}"


def test_age_valid_no_flag():
    results, _ = _run([{"paper_id": "1", "deposit_type": "OROG-AU",
                         "ages": [{"age_ma": 250.0}, {"age_ma": 1800.0}]}])
    flags = results[0]["_gate_flags"]
    assert not any("age_out_of_range" in f for f in flags)


def test_age_non_numeric_flagged():
    results, _ = _run([{"paper_id": "1", "deposit_type": "OROG-AU",
                         "ages": [{"age_ma": "bad"}, {"age_ma": 250.0}]}])
    flags = results[0]["_gate_flags"]
    assert any("age_not_numeric" in f for f in flags)


# ── 去重 ─────────────────────────────────────────────────────────────────────

def test_dedup_int_str_same_id():
    """int paper_id 和 str paper_id 视为同一篇"""
    records = [
        {"paper_id": 123, "deposit_type": "VMS"},
        {"paper_id": "123", "deposit_type": "VMS"},
    ]
    results, report = _run(records, dedup=True)
    assert report["total"] == 1, "int/str 混用应被去重为1条"
    assert report["duplicates_removed"] == 1


def test_dedup_keeps_first():
    records = [
        {"paper_id": "A", "deposit_type": "OROG-AU"},
        {"paper_id": "A", "deposit_type": "PORPHYRY-CU"},
    ]
    results, _ = _run(records, dedup=True)
    assert results[0]["deposit_type"] == "OROG-AU"


# ── deposit_type 三层漏斗 ─────────────────────────────────────────────────────

def test_alias_normalizes_hs_epith():
    results, _ = _run([{"paper_id": "1", "deposit_type": "hs-epith"}])
    assert results[0]["deposit_type"] == "EPITHERMAL-HS"
    assert any("WARN:deposit_type_normalized" in f for f in results[0]["_gate_flags"])


def test_known_uppercase_passes_silently():
    """词表内全大写类型：不触发 layer-3 FLAG"""
    results, _ = _run([{"paper_id": "1", "deposit_type": "KUPFERSCHIEFER",
                          "host_rocks": ["black shale"]}])
    flags = results[0]["_gate_flags"]
    assert not any("unknown_deposit_type" in f for f in flags)


def test_deleted_aliases_now_flag():
    """oil-shale / pge / vein 三条删除的别名应触发 FLAG，不再静默归类"""
    for dt in ["oil-shale", "pge", "vein"]:
        results, _ = _run([{"paper_id": "1", "deposit_type": dt}])
        flags = results[0]["_gate_flags"]
        assert any("FLAG:unknown_deposit_type" in f for f in flags), \
            f"删除的别名 '{dt}' 应触发 FLAG"


def test_alias_evidence_appended():
    """归一化时原始术语应追加到 deposit_type_evidence"""
    results, _ = _run([{"paper_id": "1", "deposit_type": "hs-epith",
                          "deposit_type_evidence": "high-sulfidation assemblage"}])
    ev = results[0].get("deposit_type_evidence", "")
    assert "hs-epith" in ev


# ── deposit_class ─────────────────────────────────────────────────────────────

def test_unknown_deposit_class_warns():
    results, _ = _run([{"paper_id": "1", "deposit_class": "weird_class"}])
    assert any("WARN:unknown_deposit_class" in f for f in results[0]["_gate_flags"])


def test_deposit_class_remap():
    results, _ = _run([{"paper_id": "1", "deposit_class": "tectonics"}])
    assert results[0]["deposit_class"] == "structural_tectonic"
    assert results[0]["_gate_status"] == "pass"


# ── 置信度 ──────────────────────────────────���────────────────────────────────

def test_conf_out_of_range_warns():
    results, _ = _run([{"paper_id": "1", "deposit_type_conf": 1.5}])
    assert any("conf_out_of_range" in f for f in results[0]["_gate_flags"])


def test_low_conf_flags():
    results, _ = _run([{"paper_id": "1", "deposit_type": "OROG-AU", "deposit_type_conf": 0.3}])
    assert any("FLAG:low_confidence" in f for f in results[0]["_gate_flags"])


# ── 金标回归 ─────────────────────────────────────────────────────────────────

def test_gold_standard_zero_fail():
    """100篇金标不允许任何 FAIL"""
    gold_path = Path(__file__).parent.parent / "config" / "trusted_100_papers.json"
    if not gold_path.exists():
        return  # CI 环境中允许跳过
    records = json.loads(gold_path.read_text())
    results, report = gate_check(records, dedup=False)
    fails = [r for r in results if r["_gate_status"] == "fail"]
    assert not fails, f"金标出现 FAIL: {[(r['paper_id'], r['_gate_flags']) for r in fails]}"
    assert report["fail"] == 0


def test_gold_standard_all_pass():
    """当前金标应全部 pass（非 warn）"""
    gold_path = Path(__file__).parent.parent / "config" / "trusted_100_papers.json"
    if not gold_path.exists():
        return
    records = json.loads(gold_path.read_text())
    results, report = gate_check(records, dedup=False)
    assert report["pass"] == 100, f"期待100 pass，得到 pass={report['pass']} warn={report['warn']}"
