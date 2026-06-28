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
