"""Tests for TSG Builder model support policy."""

import pytest

from error_utils import ModelTier, classify_model
from model_policy import BLOCKED_VARIANT_TOKENS, SUPPORTED_BASE_MODELS, evaluate_model_policy


@pytest.mark.unit
@pytest.mark.parametrize(
    "model_name",
    [
        "gpt-5.1",
        "gpt-5.2",
        "gpt-5.4",
        "gpt-5.5",
        "gpt-5.1-20251113",
        "gpt-5.1-2025-11-13",
        "gpt-5.2-20251211",
        "gpt-5.2-2025-12-11",
        "gpt-5.4-20260305",
        "gpt-5.4-2026-03-05",
        "gpt-5.5-20260424",
        "gpt-5.5-2026-04-24",
        " GPT-5.2 ",
    ],
)
def test_supported_base_models_pass(model_name):
    result = evaluate_model_policy(model_name)

    assert result.supported is True
    assert result.blocked_variant is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "model_name,blocked_variant",
    [
        ("gpt-5.1-chat", "chat"),
        ("gpt-5.1-mini-20260101", "mini"),
        ("gpt-5.1-nano", "nano"),
        ("gpt-5.2-chat-20260210", "chat"),
        ("gpt-5.4-codex-mini", "codex"),
        ("gpt-5.4-pro", "pro"),
        ("gpt-5.5-pro", "pro"),
    ],
)
def test_blocked_supported_model_siblings_fail(model_name, blocked_variant):
    result = evaluate_model_policy(model_name)

    assert result.supported is False
    assert result.blocked_variant == blocked_variant


@pytest.mark.unit
@pytest.mark.parametrize("base_model", sorted(SUPPORTED_BASE_MODELS))
@pytest.mark.parametrize("variant", sorted(BLOCKED_VARIANT_TOKENS))
@pytest.mark.parametrize("suffix", ["", "-20260101"])
def test_all_blocked_siblings_fail_for_each_supported_base(base_model, variant, suffix):
    model_name = f"{base_model}-{variant}{suffix}"

    result = evaluate_model_policy(model_name)

    assert result.supported is False
    assert result.blocked_variant == variant


@pytest.mark.unit
@pytest.mark.parametrize(
    "model_name",
    [
        "gpt-5.10",
        "gpt-5",
        "gpt-5-mini",
        "gpt-4.1",
        "gpt-4o",
        "gpt-5.2-preview",
    ],
)
def test_unsupported_models_fail(model_name):
    result = evaluate_model_policy(model_name)

    assert result.supported is False


@pytest.mark.unit
def test_unknown_underlying_model_remains_non_blocking():
    result = classify_model(None, "deployment-without-model-name")

    assert result.tier == ModelTier.SUPPORTED
    assert result.critical is False


@pytest.mark.unit
def test_gpt51_is_fully_supported():
    result = classify_model("gpt-5.1", "my-gpt51")

    assert result.tier == ModelTier.SUPPORTED
    assert result.critical is False


@pytest.mark.unit
def test_versioned_chat_variant_is_blocked():
    result = classify_model("gpt-5.2-chat-20260210", "chat-deployment")

    assert result.tier == ModelTier.BLOCKED
    assert result.critical is True
    assert "chat variant" in result.message