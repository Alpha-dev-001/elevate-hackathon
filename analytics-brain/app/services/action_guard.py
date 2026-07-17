"""Structural-safety guard — Layer 0, ahead of the interceptor.

Qwen's tool-call arguments are parsed through a constrained Pydantic model
BEFORE they ever become an AgentAction. The point is to make structurally-
illegal states *unrepresentable by type* rather than caught after the fact:
a negative or >100% discount, a non-positive price, an empty/whitespace
target id, a self-contradictory merge (keep an id you're also removing), an
invalid copy target, or a non-positive sale duration cannot be constructed
into a valid action at all — they raise ActionValidationError and the
decision cycle declines, exactly like Qwen declining to act.

This is deliberately distinct from the interceptor (interceptor.py). The
interceptor's job is to CLAMP a valid-but-too-aggressive value (a 60%
discount pulled down to the merchant's ceiling) and to HARD-BLOCK on live
business state (price below cost, stock below zero). This layer rejects
values that are not "aggressive" but *nonsensical* — the fingerprint of a
hallucinated tool call, not a bold-but-legal business move. Belt and
suspenders: a bad value that somehow slips past here still hits the
interceptor; a merely-aggressive value that passes here still gets clamped
there. Neither layer is redundant with the other.

Pure — no I/O, no DB, no Qwen. Trivially testable (see test_action_guard.py).
"""
from __future__ import annotations

from typing import Annotated, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

# ── Reusable constrained primitives ────────────────────────────────────────
# A store id/label is a non-empty string once surrounding whitespace is
# stripped — "" and "   " are both phantom targets, not real ones.
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# A discount is a percentage: it cannot be negative and cannot exceed 100%.
# (The merchant's own, lower ceiling is enforced downstream by the interceptor.)
Percent = Annotated[float, Field(ge=0, le=100)]
# A live price is strictly positive. Below-cost is the interceptor's concern;
# zero or negative is not even a price.
PositivePrice = Annotated[float, Field(gt=0)]
# A sale that lasts zero or negative minutes is not a sale.
PositiveInt = Annotated[int, Field(gt=0)]


class ActionValidationError(ValueError):
    """Raised when tool-call args encode a structurally-illegal state."""


class _ArgModel(BaseModel):
    # extra="allow" so narrative/reasoning fields Qwen sends alongside the
    # safety-critical params survive validation untouched — we constrain the
    # dangerous fields, we don't strip the rest.
    model_config = ConfigDict(extra="allow")


class FlashSaleArgs(_ArgModel):
    product_id: NonEmptyStr
    discount_percent: Percent
    duration_minutes: Optional[PositiveInt] = None


class ScarcityPriceArgs(_ArgModel):
    product_id: NonEmptyStr
    discount_percent: Percent


class LayoutMorphArgs(_ArgModel):
    # Enum membership for the variant is normalized downstream by
    # layout_dsl.coerce_variant; here we only reject a structurally-empty grid.
    new_grid: NonEmptyStr


class RecoveryOfferArgs(_ArgModel):
    discount_percent: Percent


class CopyRewriteArgs(_ArgModel):
    target: Annotated[str, StringConstraints(strip_whitespace=True)]
    product_id: Optional[NonEmptyStr] = None

    @model_validator(mode="after")
    def _known_target(self) -> "CopyRewriteArgs":
        if self.target not in ("hero_headline", "product_description", "section_copy"):
            raise ValueError(f"unknown copy target: {self.target!r}")
        return self


class DuplicateMergeArgs(_ArgModel):
    keep_product_id: NonEmptyStr
    remove_product_ids: list[NonEmptyStr] = Field(min_length=1)

    @model_validator(mode="after")
    def _keep_not_removed(self) -> "DuplicateMergeArgs":
        if self.keep_product_id in self.remove_product_ids:
            raise ValueError("keep_product_id cannot also be in remove_product_ids")
        return self


class FeatureProductArgs(_ArgModel):
    product_id: NonEmptyStr
    featured_label: NonEmptyStr


class PriceRebalanceArgs(_ArgModel):
    product_id: NonEmptyStr
    new_price: PositivePrice


class CartDwellNudgeArgs(_ArgModel):
    discount_percent: Percent


_MODELS: dict[str, type[_ArgModel]] = {
    "propose_flash_sale": FlashSaleArgs,
    "propose_scarcity_price": ScarcityPriceArgs,
    "propose_layout_morph": LayoutMorphArgs,
    "propose_recovery_offer": RecoveryOfferArgs,
    "propose_copy_rewrite": CopyRewriteArgs,
    "propose_duplicate_merge": DuplicateMergeArgs,
    "propose_feature_product": FeatureProductArgs,
    "propose_price_rebalance": PriceRebalanceArgs,
    "propose_cart_dwell_nudge": CartDwellNudgeArgs,
}


def _summarize(exc: ValidationError) -> str:
    """One compact human-readable line from a Pydantic error, for the
    decision log / receipt note."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ())) or "<root>"
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts)


def validate_tool_args(tool_name: str, args: dict) -> dict:
    """Structurally validate Qwen's tool-call arguments.

    Returns the normalized args dict (numeric strings coerced, whitespace
    stripped, extra fields preserved) on success. Raises
    ActionValidationError if the args encode a structurally-illegal state.

    Unknown tool names pass through unchanged — the guard makes no claim
    about tools it doesn't model; those are handled at the dispatch layer.
    """
    model = _MODELS.get(tool_name)
    if model is None:
        return dict(args or {})
    try:
        validated = model.model_validate(args or {})
    except ValidationError as exc:
        raise ActionValidationError(_summarize(exc)) from exc
    return validated.model_dump(exclude_none=True)
