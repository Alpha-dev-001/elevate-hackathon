"""Qwen's own judgment on whether a dropped image is actually a logo — no
input-type validation existed before this: any reachable image, logo or
not, flowed straight into brand generation and produced a confident-
looking (but nonsensical) brand. LogoAnalysis.is_logo (default True, so a
compliant response that simply omits the new field falls back to the old
"just trust it" behavior) is Qwen's explicit call; an explicit False stops
analyze_logo before generate_brand is ever reached."""
import json
from unittest.mock import AsyncMock, patch

import pytest


def _qwen_json(payload: dict) -> str:
    return json.dumps(payload)


def _logo_payload(**overrides) -> dict:
    base = {
        "is_logo": True,
        "rejection_reason": None,
        "primary_colors": ["#112233"],
        "secondary_colors": [],
        "mood": "bold",
        "style": "geometric",
        "geometry_notes": "sharp angles, high contrast",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
class TestLogoRejection:
    async def test_a_real_logo_is_returned_normally(self):
        from app.services.brand import analyze_logo

        with patch("app.services.brand._qwen_chat", new=AsyncMock(return_value=_qwen_json(_logo_payload()))):
            result = await analyze_logo("https://example.com/logo.png")

        assert result.is_logo is True
        assert result.primary_colors == ["#112233"]

    async def test_qwen_rejecting_the_image_raises_before_brand_generation(self):
        from app.services.brand import analyze_logo, BrandGenerationError

        payload = _logo_payload(is_logo=False, rejection_reason="a photo of a beach")
        with patch("app.services.brand._qwen_chat", new=AsyncMock(return_value=_qwen_json(payload))):
            with pytest.raises(BrandGenerationError) as exc_info:
                await analyze_logo("https://example.com/beach.jpg")

        assert "beach" in str(exc_info.value)

    async def test_build_brand_package_never_calls_generate_brand_on_rejection(self):
        """The actual integration guarantee: generate_brand must not run at
        all when the image is rejected, not just that analyze_logo raises."""
        from app.services.brand import build_brand_package

        payload = _logo_payload(is_logo=False, rejection_reason="a selfie")
        with patch("app.services.brand._qwen_chat", new=AsyncMock(return_value=_qwen_json(payload))), \
             patch("app.services.brand.generate_brand", new=AsyncMock()) as mock_generate:
            from app.services.brand import BrandGenerationError
            with pytest.raises(BrandGenerationError):
                await build_brand_package("https://example.com/selfie.jpg", "Test Store", "fashion", "desc")

        mock_generate.assert_not_awaited()

    async def test_missing_is_logo_field_falls_back_to_true_not_a_validation_error(self):
        """A compliant-but-older-style response (field simply absent, not an
        explicit rejection) must not spuriously block a real logo — only an
        explicit False does."""
        from app.services.brand import analyze_logo

        payload = _logo_payload()
        del payload["is_logo"]
        del payload["rejection_reason"]
        with patch("app.services.brand._qwen_chat", new=AsyncMock(return_value=_qwen_json(payload))):
            result = await analyze_logo("https://example.com/logo.png")

        assert result.is_logo is True
