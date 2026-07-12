from app.services.css_gen import sanitize_css


def test_strips_forbidden_constructs():
    css = '[data-store="haree"] .product-card { transform: scale(1.02); background: url(http://x/y.png); }\n@import "evil.css";'
    out = sanitize_css(css, "haree")
    assert "url(" not in out and "@import" not in out


def test_drops_unscoped_rules():
    css = 'body { display: none; }\n[data-store="haree"] .hero-title { letter-spacing: 0.2em; }'
    out = sanitize_css(css, "haree")
    assert "body {" not in out
    assert "letter-spacing" in out


def test_position_fixed_and_zindex_removed():
    css = '[data-store="haree"] .product-price { position: fixed; z-index: 999; opacity: 0.8; }'
    out = sanitize_css(css, "haree")
    assert "position" not in out and "z-index" not in out


def test_disallowed_property_dropped():
    """ALLOWED_PROPS was declared but never actually checked -- a scoped,
    non-forbidden-pattern rule using a property outside the allowlist (e.g.
    width, background-color) used to pass straight through."""
    css = '[data-store="haree"] .nav-link { width: 500px; }'
    out = sanitize_css(css, "haree")
    assert out == ""


def test_mixed_allowed_and_disallowed_drops_whole_line():
    """One rule per line -- if any property on the line isn't allowed, the
    whole line is dropped rather than partially rewritten."""
    css = '[data-store="haree"] .nav-link { font-size: 1.2em; width: 500px; }'
    out = sanitize_css(css, "haree")
    assert out == ""


def test_nav_selectors_with_new_allowed_properties_kept():
    css = '\n'.join([
        '[data-store="haree"] .nav-link { font-size: 1.2em; }',
        '[data-store="haree"] .nav-links { gap: 2rem; }',
    ])
    out = sanitize_css(css, "haree")
    assert "font-size: 1.2em" in out
    assert "gap: 2rem" in out
