"""Model deployment policy for TSG Builder."""

from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_BASE_MODELS = frozenset({"gpt-5.1", "gpt-5.2", "gpt-5.4", "gpt-5.5"})
BLOCKED_VARIANT_TOKENS = frozenset({"chat", "mini", "nano", "pro", "codex"})
SUPPORTED_MODELS_DISPLAY = ", ".join(sorted(SUPPORTED_BASE_MODELS))


@dataclass(frozen=True)
class ModelPolicyResult:
    """Result of applying TSG Builder's model support policy."""

    model_name: str
    base_model: str | None
    supported: bool
    blocked_variant: str | None = None


def evaluate_model_policy(model_name: str | None) -> ModelPolicyResult:
    """Evaluate whether a model name matches the supported non-chat base models."""
    normalized = (model_name or "").strip().lower()
    if not normalized:
        return ModelPolicyResult(model_name="", base_model=None, supported=True)

    matched_base = _match_supported_base(normalized)
    if not matched_base:
        return ModelPolicyResult(model_name=normalized, base_model=None, supported=False)

    remainder = normalized[len(matched_base):]
    if not remainder:
        return ModelPolicyResult(model_name=normalized, base_model=matched_base, supported=True)

    if not remainder.startswith("-"):
        return ModelPolicyResult(model_name=normalized, base_model=None, supported=False)

    remaining_tokens = [token for token in remainder[1:].split("-") if token]
    for token in remaining_tokens:
        if token in BLOCKED_VARIANT_TOKENS:
            return ModelPolicyResult(
                model_name=normalized,
                base_model=matched_base,
                supported=False,
                blocked_variant=token,
            )

    if remaining_tokens and all(token.isdigit() for token in remaining_tokens):
        return ModelPolicyResult(model_name=normalized, base_model=matched_base, supported=True)

    return ModelPolicyResult(model_name=normalized, base_model=matched_base, supported=False)


def _match_supported_base(model_name: str) -> str | None:
    for base_model in sorted(SUPPORTED_BASE_MODELS, key=len, reverse=True):
        if model_name == base_model or model_name.startswith(f"{base_model}-"):
            return base_model
    return None
