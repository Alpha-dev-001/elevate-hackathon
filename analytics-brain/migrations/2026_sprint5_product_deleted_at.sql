-- is_active=False alone is ambiguous: it means either "never approved" (pending)
-- or "soft-deleted" (used to be live). deleted_at disambiguates, so a soft-deleted
-- product with price/trust history no longer resurfaces in the pending-approval
-- queue and delete_product doesn't attempt a hard delete that FK-violates against
-- product_price_history/autopilot_trust. Idempotent.
ALTER TABLE products ADD COLUMN IF NOT EXISTS deleted_at BIGINT;
