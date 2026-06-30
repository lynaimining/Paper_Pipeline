"""process_paper.py 核心函数测试"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from process_paper import (
    normalize_coordinates,
    normalize_commodities,
    load_jsonl,
    quality_score,
    rewrite_image_path,
)


# ── normalize_coordinates ────────────────────────────────────────────────────

def test_coord_zero_lat_preserved():
    """lat=0.0 不被 or 短路——与 gate_lite 同款 bug 的 process_paper 镜像"""
    result = normalize_coordinates({"lat": 0.0, "lon": 35.5})
    assert result is not None
    assert result["lat"] == 0.0


def test_coord_zero_lon_preserved():
    result = normalize_coordinates({"lat": 51.5, "lon": 0.0})
    assert result is not None
    assert result["lon"] == 0.0


def test_coord_dict_standard():
    result = normalize_coordinates({"lat": -33.9, "lon": 151.2})
    assert result == {"lat": -33.9, "lon": 151.2}


def test_coord_latitude_alias():
    result = normalize_coordinates({"latitude": 45.0, "longitude": -75.0})
    assert result == {"lat": 45.0, "lon": -75.0}


def test_coord_list_form():
    result = normalize_coordinates([10.5, 20.3])
    assert result == {"lat": 10.5, "lon": 20.3}


def test_coord_dms_string():
    result = normalize_coordinates("12°24'30\"S, 131°12'45\"E")
    assert result is not None
    assert abs(result["lat"] - (-12.408333)) < 0.001
    assert abs(result["lon"] - 131.2125) < 0.001


def test_coord_none_returns_none():
    assert normalize_coordinates(None) is None


def test_coord_invalid_returns_none():
    assert normalize_coordinates("not a coordinate") is None


# ── normalize_commodities ────────────────────────────────────────────────────

def test_comm_new_format_passthrough():
    raw = {"primary": ["Au", "Ag"], "byproduct": ["Cu"], "trace": []}
    result = normalize_commodities(raw)
    assert result["primary"] == ["Au", "Ag"]
    assert result["byproduct"] == ["Cu"]


def test_comm_flat_list():
    result = normalize_commodities(["Au", "Ag", "Cu"])
    assert result["primary"] == ["Au", "Ag", "Cu"]
    assert result["byproduct"] == []


def test_comm_string():
    result = normalize_commodities("Au")
    assert result["primary"] == ["Au"]


def test_comm_none():
    assert normalize_commodities(None) is None


def test_comm_list_with_dicts_skips_none():
    """列表中含 None 应过滤"""
    result = normalize_commodities(["Au", None, "Ag"])
    assert None not in result["primary"]
    assert "Au" in result["primary"]


# ── load_jsonl ───────────────────────────────────────────────────────────────

def test_load_jsonl_good_lines():
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        fname = f.name
        f.write(json.dumps({"id": "a"}) + "\n")
        f.write(json.dumps({"id": "b"}) + "\n")
    try:
        result = load_jsonl(fname)
        assert len(result) == 2
        assert result[0]["id"] == "a"
    finally:
        os.unlink(fname)


def test_load_jsonl_bad_line_skipped():
    """坏行跳过，好行保留"""
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        fname = f.name
        f.write(json.dumps({"id": "ok1"}) + "\n")
        f.write("{bad json\n")
        f.write(json.dumps({"id": "ok2"}) + "\n")
    try:
        result = load_jsonl(fname)
        assert len(result) == 2
        assert result[0]["id"] == "ok1"
        assert result[1]["id"] == "ok2"
    finally:
        os.unlink(fname)


def test_load_jsonl_missing_file():
    result = load_jsonl("/nonexistent/path.jsonl")
    assert result == []


def test_load_jsonl_none_path():
    result = load_jsonl(None)
    assert result == []


# ── quality_score ────────────────────────────────────────────────────────────

def test_quality_score_pass_tier():
    score = quality_score({"has_ground_truth": True, "confidence": 1.0,
                            "tier": "pass", "n_body_refs": 3})
    assert abs(score - (0.4 + 0.3 + 0.1 + 0.2)) < 0.001


def test_quality_score_warn_tier():
    score = quality_score({"has_ground_truth": True, "confidence": 1.0,
                            "tier": "warn", "n_body_refs": 0})
    assert abs(score - (0.4 + 0.3 + 0.05)) < 0.001


def test_quality_score_fail_tier():
    score = quality_score({"has_ground_truth": True, "confidence": 1.0,
                            "tier": "fail", "n_body_refs": 0})
    assert abs(score - (0.4 + 0.3)) < 0.001


def test_quality_score_legacy_gold():
    score_new = quality_score({"has_ground_truth": True, "confidence": 1.0,
                                "tier": "pass", "n_body_refs": 0})
    score_old = quality_score({"has_ground_truth": True, "confidence": 1.0,
                                "tier": "gold", "n_body_refs": 0})
    assert abs(score_new - score_old) < 0.001


def test_quality_score_bounds():
    score = quality_score({"has_ground_truth": True, "confidence": 1.0,
                            "tier": "pass", "n_body_refs": 99})
    assert 0.0 <= score <= 1.0


# ── symlink guard ────────────────────────────────────────────────────────────

def test_rewrite_image_path_broken_symlink():
    """断裂 symlink 不触发 FileExistsError"""
    with tempfile.TemporaryDirectory() as d:
        images_dir = Path(d) / "images"
        fake_src = Path(d) / "img.jpg"
        fake_src.write_bytes(b"fake")

        # 第一次：正常创建
        rel, dest = rewrite_image_path(str(fake_src), "p1", images_dir)
        assert dest.is_symlink()

        # 删除原始文件，制造断裂 symlink
        fake_src.unlink()
        assert not dest.exists()
        assert dest.is_symlink()

        # 第二次：不应抛 FileExistsError
        try:
            rewrite_image_path(str(fake_src), "p1", images_dir)
        except FileExistsError as e:
            raise AssertionError(f"断裂 symlink 触发了 FileExistsError: {e}")
