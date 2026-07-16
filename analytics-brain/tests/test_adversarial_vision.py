"""
Adversarial tests for product vision — edge cases when wrong images are dropped.

These tests mock the Qwen VL response to simulate what happens when:
- A selfie is dropped instead of a product photo
- An irrelevant image (landscape, meme, code screenshot) is uploaded
- Qwen returns low confidence or garbage
- Multiple products are in one image
- The image is blank/solid color

The function under test is analyze_product_image() from app.services.vision.
"""
from __future__ import annotations

import asyncio
import os
import sys

# Ensure the analytics-brain root is on the path so `app.*` imports resolve
# when running directly (``python tests/test_adversarial_vision.py``).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, AsyncMock

import httpx

from app.services.vision import analyze_product_image, ProductVision, is_probably_image


# ─── Helpers ──────────────────────────────────────────────────────────────────

BASELINE = 50.0
STORE = "Test Fashion Boutique"
VOICE = "modern, confident"


def _call(mock_json_response: dict) -> ProductVision:
    """Patch _qwen_chat and _extract_json, call analyze_product_image."""
    async def _run():
        with (
            patch("app.services.vision._qwen_chat", new_callable=AsyncMock) as mock_chat,
            patch("app.services.vision._extract_json", return_value=mock_json_response),
        ):
            mock_chat.return_value = "{}"  # doesn't matter — _extract_json is mocked
            return await analyze_product_image(
                image_ref="https://example.com/test.jpg",
                store_name=STORE,
                brand_voice=VOICE,
                baseline_price=BASELINE,
            )

    return asyncio.run(_run())


# ── Confidence / identity ─────────────────────────────────────────────────────


def test_selfie_returns_not_confident():
    """A selfie dropped instead of a product photo → confident=False."""
    result = _call({
        "name": "Person",
        "confident": False,
        "suggested_price": 50,
        "category": "other",
    })
    assert result.confident is False
    assert result.name == "Person"


def test_unidentified_item():
    """Completely ambiguous image → Qwen follows prompt and says so."""
    result = _call({
        "name": "Unidentified item",
        "confident": False,
        "suggested_price": 50,
        "category": "other",
    })
    assert result.confident is False
    assert result.name == "Unidentified item"


def test_landscape_image_low_confidence():
    """A landscape photo instead of a product → confident=False."""
    result = _call({
        "name": "Mountain landscape",
        "confident": False,
        "suggested_price": 50,
        "category": "other",
    })
    assert result.confident is False


def test_screenshot_wrong_category():
    """A code screenshot — Qwen identifies it but category is 'other'.

    This is a known gap: confident=True with category=other means the
    model *thinks* it knows what it is but can't fit it into a product
    category. In production we'd flag this for merchant review.
    """
    result = _call({
        "name": "Code editor",
        "confident": True,
        "suggested_price": 50,
        "category": "other",
    })
    assert result.confident is True
    assert result.category == "other"


def test_multiple_products_first_wins():
    """Multiple products in one image — Qwen picks one, we accept it."""
    result = _call({
        "name": "Leather Slides",
        "confident": True,
        "suggested_price": 45,
        "category": "slides",
        "colors": ["brown", "black"],
    })
    assert result.name == "Leather Slides"
    assert result.confident is True
    assert result.suggested_price == 45.0
    assert result.colors == ["brown", "black"]


# ── Price clamping ────────────────────────────────────────────────────────────


def test_price_clamped_to_upper_bound():
    """Absurdly high price → clamped to 2× baseline."""
    result = _call({
        "name": "Generic Item",
        "suggested_price": 999,
    })
    assert result.suggested_price == 100.0  # 2× 50.0


def test_price_clamped_to_lower_bound():
    """Absurdly low price → clamped to 0.6× baseline."""
    result = _call({
        "name": "Generic Item",
        "suggested_price": 1,
    })
    assert result.suggested_price == 30.0  # 0.6× 50.0


def test_price_within_range_unchanged():
    """Price within [0.6×, 2×] passes through untouched."""
    result = _call({
        "name": "Generic Item",
        "suggested_price": 60,
    })
    assert result.suggested_price == 60.0


def test_garbage_price_defaults_to_baseline():
    """Non-numeric price string → fallback to baseline."""
    result = _call({
        "name": "Generic Item",
        "suggested_price": "not_a_number",
    })
    assert result.suggested_price == BASELINE


def test_null_price_defaults_to_baseline():
    """None price → fallback to baseline."""
    result = _call({
        "name": "Generic Item",
        "suggested_price": None,
    })
    assert result.suggested_price == BASELINE


def test_missing_price_defaults_to_baseline():
    """Missing suggested_price key → fallback to baseline."""
    result = _call({
        "name": "Generic Item",
    })
    assert result.suggested_price == BASELINE


def test_zero_price_clamped_to_lower_bound():
    """Zero price → explicit None check means 0 is kept, then clamped to 0.6× baseline.

    FIXED: was previously `0 or baseline_price` which treated 0 as missing.
    Now uses explicit `if raw_price is not None` so 0 flows through to clamping.
    """
    result = _call({
        "name": "Generic Item",
        "suggested_price": 0,
    })
    assert result.suggested_price == 30.0  # 0 clamped to 0.6× baseline


def test_negative_price_clamped_to_lower():
    """Negative price → clamped to 0.6× baseline."""
    result = _call({
        "name": "Generic Item",
        "suggested_price": -100,
    })
    assert result.suggested_price == 30.0


# ── Color sanitization ────────────────────────────────────────────────────────


def test_colors_sanitized():
    """Colors: lowered, stripped, empties removed, max 6."""
    result = _call({
        "name": "Test Product",
        "suggested_price": 50,
        "colors": ["BLACK", "  Blue  ", "", "red", "green", "yellow", "purple"],
    })
    # "BLACK" → "black", "  Blue  " → "blue", "" stripped away
    # Remaining 6 after filter: black, blue, red, green, yellow, purple
    assert result.colors == ["black", "blue", "red", "green", "yellow", "purple"]
    assert len(result.colors) <= 6


def test_colors_not_a_list():
    """String instead of list → wrapped into single-element list."""
    result = _call({
        "name": "Test Product",
        "suggested_price": 50,
        "colors": "black",
    })
    assert result.colors == ["black"]


def test_colors_null_becomes_empty():
    """Null colors → empty list."""
    result = _call({
        "name": "Test Product",
        "suggested_price": 50,
        "colors": None,
    })
    assert result.colors == []


def test_colors_missing_becomes_empty():
    """Missing colors key → empty list."""
    result = _call({
        "name": "Test Product",
        "suggested_price": 50,
    })
    assert result.colors == []


def test_colors_all_whitespace_removed():
    """Colors that are only whitespace → filtered out entirely."""
    result = _call({
        "name": "Test Product",
        "suggested_price": 50,
        "colors": ["  ", "\t", "red"],
    })
    assert result.colors == ["red"]


# ── Name / brand truncation ───────────────────────────────────────────────────


def test_name_truncated_to_120_chars():
    """Absurdly long name → truncated to 120 characters."""
    long_name = "A" * 500
    result = _call({
        "name": long_name,
        "suggested_price": 50,
    })
    assert len(result.name) == 120
    assert result.name == "A" * 120


def test_brand_truncated_to_60_chars():
    """Absurdly long brand → truncated to 60 characters."""
    long_brand = "B" * 200
    result = _call({
        "name": "Test Product",
        "brand": long_brand,
        "suggested_price": 50,
    })
    assert len(result.brand) == 60
    assert result.brand == "B" * 60


def test_empty_name_defaults_to_unidentified():
    """Empty name string → 'Unidentified item'."""
    result = _call({
        "name": "",
        "suggested_price": 50,
    })
    assert result.name == "Unidentified item"


def test_null_name_defaults_to_unidentified():
    """Null name → 'Unidentified item'."""
    result = _call({
        "name": None,
        "suggested_price": 50,
    })
    assert result.name == "Unidentified item"


def test_whitespace_only_name_defaults_to_unidentified():
    """Whitespace-only name → strip first, then fall back to 'Unidentified item'.

    FIXED: was previously `"   " or "Unidentified item"` which kept the spaces
    (truthy), then strip made it empty. Now strips BEFORE the fallback check.
    """
    result = _call({
        "name": "   ",
        "suggested_price": 50,
    })
    assert result.name == "Unidentified item"


# ── Category normalization ────────────────────────────────────────────────────


def test_category_lowered():
    """Uppercase category → normalized to lowercase."""
    result = _call({
        "name": "Nike Air Max",
        "suggested_price": 50,
        "category": "SNEAKERS",
    })
    assert result.category == "sneakers"


def test_category_missing_defaults_to_other():
    """Missing category → 'other'."""
    result = _call({
        "name": "Test Product",
        "suggested_price": 50,
    })
    assert result.category == "other"


def test_category_truncated_to_40():
    """Overly long category → truncated to 40 chars."""
    result = _call({
        "name": "Test Product",
        "suggested_price": 50,
        "category": "a" * 100,
    })
    assert len(result.category) == 40


# ── Pre-flight URL validity check ─────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code=200, content_type="image/jpeg"):
        self.status_code = status_code
        self.headers = {"content-type": content_type} if content_type else {}


class _FakeAsyncClient:
    """Mimics httpx.AsyncClient's async context manager + head/get, for a
    single test-controlled response per call."""
    def __init__(self, head_response=None, get_response=None, raise_exc=None):
        self._head_response = head_response
        self._get_response = get_response
        self._raise_exc = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def head(self, url):
        if self._raise_exc:
            raise self._raise_exc
        return self._head_response

    async def get(self, url, headers=None):
        return self._get_response


def _patch_client(monkeypatch, client):
    import app.services.vision as vision_mod
    monkeypatch.setattr(vision_mod.httpx, "AsyncClient", lambda **kw: client)


def test_dead_url_returns_false(monkeypatch):
    _patch_client(monkeypatch, _FakeAsyncClient(head_response=_FakeResponse(404)))
    assert asyncio.run(is_probably_image("https://example.com/dead.jpg")) is False


def test_non_image_content_type_returns_false(monkeypatch):
    _patch_client(monkeypatch, _FakeAsyncClient(
        head_response=_FakeResponse(200, content_type="text/html")
    ))
    assert asyncio.run(is_probably_image("https://example.com/page.html")) is False


def test_valid_image_returns_true(monkeypatch):
    _patch_client(monkeypatch, _FakeAsyncClient(
        head_response=_FakeResponse(200, content_type="image/png")
    ))
    assert asyncio.run(is_probably_image("https://example.com/photo.png")) is True


def test_head_not_supported_falls_back_to_ranged_get(monkeypatch):
    _patch_client(monkeypatch, _FakeAsyncClient(
        head_response=_FakeResponse(405),
        get_response=_FakeResponse(206, content_type="image/webp"),
    ))
    assert asyncio.run(is_probably_image("https://cdn.example.com/photo.webp")) is True


def test_timeout_is_inconclusive_returns_true(monkeypatch):
    """A network blip must never block a real photo — Qwen's own fetch is
    the tie-breaker when the pre-check can't tell either way."""
    _patch_client(monkeypatch, _FakeAsyncClient(raise_exc=httpx.TimeoutException("timed out")))
    assert asyncio.run(is_probably_image("https://example.com/slow.jpg")) is True


def test_missing_content_type_header_is_inconclusive_returns_true(monkeypatch):
    _patch_client(monkeypatch, _FakeAsyncClient(head_response=_FakeResponse(200, content_type=None)))
    assert asyncio.run(is_probably_image("https://example.com/no-header.jpg")) is True


# ── Confidence edge cases ─────────────────────────────────────────────────────


def test_confident_missing_defaults_to_false():
    """Missing 'confident' key means Qwen's JSON didn't match the contract —
    defaults to False so it goes to merchant review rather than going live
    silently on an incomplete response."""
    result = _call({
        "name": "Leather Slides",
        "suggested_price": 50,
    })
    assert result.confident is False


def test_confident_true_but_no_name_forced_false():
    """Qwen claims confident=True but gave no usable name — contradictory,
    so 'confident' is forced False regardless of the claimed value."""
    result = _call({
        "confident": True,
        "suggested_price": 50,
    })
    assert result.confident is False
    assert result.name == "Unidentified item"


def test_confident_truthy_int_zero():
    """Qwen sometimes returns 1/0 instead of true/false — 0 → False."""
    result = _call({
        "name": "Test Product",
        "suggested_price": 50,
        "confident": 0,
    })
    assert result.confident is False


def test_confident_truthy_int_one():
    """Qwen returns 1 → True."""
    result = _call({
        "name": "Test Product",
        "suggested_price": 50,
        "confident": 1,
    })
    assert result.confident is True


# ── Full integration-style mocks ──────────────────────────────────────────────


def test_full_valid_response():
    """Happy path: fully valid Qwen response passes through cleanly."""
    result = _call({
        "name": "Nautica Logo Slides",
        "brand": "Nautica",
        "description": "Clean slides with bold branding for everyday wear.",
        "category": "slides",
        "colors": ["navy", "white"],
        "suggested_price": 55,
        "confident": True,
    })
    assert result.name == "Nautica Logo Slides"
    assert result.brand == "Nautica"
    assert result.description == "Clean slides with bold branding for everyday wear."
    assert result.category == "slides"
    assert result.colors == ["navy", "white"]
    assert result.suggested_price == 55.0
    assert result.confident is True


def test_blank_image_response():
    """Solid color / blank image — Qwen can't identify anything."""
    result = _call({
        "name": "Unidentified item",
        "brand": "",
        "description": "",
        "category": "other",
        "colors": [],
        "suggested_price": 50,
        "confident": False,
    })
    assert result.confident is False
    assert result.name == "Unidentified item"
    assert result.colors == []
    assert result.brand == ""
