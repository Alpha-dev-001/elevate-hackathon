-- Dynamic Baseline Pricing (2026-07-14): merchant-set anchor Qwen's pricing
-- autopilot reasons around. Backfilled to the product's current price so an
-- existing store that never touches this feature sees zero behavior change.
ALTER TABLE products ADD COLUMN IF NOT EXISTS baseline_price DOUBLE PRECISION;
UPDATE products SET baseline_price = price WHERE baseline_price IS NULL;
ALTER TABLE products ALTER COLUMN baseline_price SET NOT NULL;
ALTER TABLE products ALTER COLUMN baseline_price SET DEFAULT 0.0;
