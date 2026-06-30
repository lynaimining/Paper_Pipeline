"""
deepseek_extract.py 关键路径测试

只测可以脱离 API 验证的逻辑：
  1. JSON 修复路径（```json...``` 格式）
  2. 429 限流检测
  3. prompt_hash 覆盖 SYSTEM_PROMPT + USER_TEMPLATE
  4. load_body BOM 剥离
  5. _estimate_cost_usd 费用计算
"""
import asyncio
import sys
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import deepseek_extract as de


# ── _prompt_hash ─────────────────────────────────────────────────────────────

def test_prompt_hash_covers_system_prompt():
    original = de._prompt_hash()
    original_system = de.SYSTEM_PROMPT
    try:
        de.SYSTEM_PROMPT = de.SYSTEM_PROMPT + " MODIFIED"
        assert de._prompt_hash() != original, "SYSTEM_PROMPT 变更未导致 hash 变化"
    finally:
        de.SYSTEM_PROMPT = original_system


def test_prompt_hash_covers_user_template():
    original = de._prompt_hash()
    original_template = de.USER_TEMPLATE
    try:
        de.USER_TEMPLATE = de.USER_TEMPLATE + " MODIFIED"
        assert de._prompt_hash() != original, "USER_TEMPLATE 变更未导致 hash 变化"
    finally:
        de.USER_TEMPLATE = original_template


# ── load_body ────────────────────────────────────────────────────────────────

def test_load_body_strips_bom():
    with tempfile.NamedTemporaryFile("wb", suffix=".md", delete=False) as f:
        fname = f.name
        f.write(b"\xef\xbb\xbf# BOM prefixed content\nBody here.")
    try:
        text = de.load_body(fname)
        assert text[0] != "﻿", "BOM 应被 utf-8-sig 剥离"
        assert text.startswith("# BOM"), f"内容读取错误: {text[:30]}"
    finally:
        os.unlink(fname)


def test_load_body_truncate():
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as f:
        fname = f.name
        f.write("A" * 5000)
    try:
        text = de.load_body(fname, truncate=100)
        assert len(text) == 100
    finally:
        os.unlink(fname)


def test_load_body_removes_references_section():
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as f:
        fname = f.name
        f.write("Main body.\n# References\n[1] Smith et al.")
    try:
        text = de.load_body(fname)
        assert "References" not in text
        assert "Main body" in text
    finally:
        os.unlink(fname)


# ── _estimate_cost_usd ───────────────────────────────────────────────────────

def test_estimate_cost_correct():
    acc = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
    cost = de._estimate_cost_usd(acc)
    expected = de._PRICE_INPUT_PER_M + de._PRICE_OUTPUT_PER_M
    assert abs(cost - expected) < 1e-9


def test_estimate_cost_zero():
    assert de._estimate_cost_usd({"prompt_tokens": 0, "completion_tokens": 0}) == 0.0


def test_estimate_cost_missing_keys():
    # 缺字段时不应 crash（get 有默认值）
    assert de._estimate_cost_usd({}) == 0.0


# ── extract_one：429 限流检测 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_one_detects_rate_limit(caplog):
    """429 异常应触发 60s 等待路径，而不是普通退避。"""
    import logging

    paper = {"paper_id": "test_paper", "md_path": "/nonexistent.md"}
    semaphore = asyncio.Semaphore(1)
    usage_acc = {"prompt_tokens": 0, "completion_tokens": 0,
                 "total_tokens": 0, "api_calls": 0}

    # load_body 会在 try 块外被调用，需要一个可读文件
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as f:
        fname = f.name
        f.write("Test geological content.")
    paper["md_path"] = fname

    class FakeRateLimitError(Exception):
        pass

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        raise FakeRateLimitError("429 Too Many Requests: rate limit exceeded")

    fake_client = MagicMock()
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = fake_create

    # 让 sleep 不真的等
    sleep_durations = []

    async def fake_sleep(t):
        sleep_durations.append(t)

    try:
        with patch("asyncio.sleep", side_effect=fake_sleep):
            with caplog.at_level(logging.WARNING, logger="deepseek_extract"):
                result = await de.extract_one(
                    fake_client, paper, truncate=100,
                    semaphore=semaphore, usage_acc=usage_acc, retries=2
                )

        assert result is None  # 重试耗尽后返回 None
        # 429 路径应触发 60s 等待（不是普通的 1-3s 退避）
        assert any(d >= 60.0 for d in sleep_durations), (
            f"429 应触发 60s 等待，实际 sleep 序列: {sleep_durations}"
        )
    finally:
        os.unlink(fname)


# ── extract_one：JSON 修复路径 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_one_json_repair():
    """模型输出 ```json...``` 格式时应能正确修复并返回结果。"""
    paper = {"paper_id": "repair_test", "md_path": ""}
    semaphore = asyncio.Semaphore(1)
    usage_acc = {"prompt_tokens": 0, "completion_tokens": 0,
                 "total_tokens": 0, "api_calls": 0}

    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as f:
        fname = f.name
        f.write("Geological paper body.")
    paper["md_path"] = fname

    valid_json = '{"deposit_type": "OROG-AU", "deposit_class": "mineral_deposit"}'
    model_output = f"Sure! Here is the JSON:\n```json\n{valid_json}\n```"

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = model_output
    mock_resp.usage = None

    async def fake_create(**kwargs):
        return mock_resp

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create

    try:
        result = await de.extract_one(
            fake_client, paper, truncate=0,
            semaphore=semaphore, usage_acc=usage_acc, retries=1
        )
        assert result is not None, "JSON 修复路径应返回结果"
        assert result.get("deposit_type") == "OROG-AU"
        assert result.get("paper_id") == "repair_test"
    finally:
        os.unlink(fname)
