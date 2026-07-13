-- Proactive Product Featuring trigger (2026-07-13): one product per store can
-- be marked featured, with Qwen's own badge copy, surfaced first in the
-- customer-facing product list (see store.py). No DSL/layout change needed.
ALTER TABLE products ADD COLUMN IF NOT EXISTS is_featured BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE products ADD COLUMN IF NOT EXISTS featured_label VARCHAR;
