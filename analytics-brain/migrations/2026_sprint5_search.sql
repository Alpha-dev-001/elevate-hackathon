-- Store-wide search-demand tracking: every storefront search query is logged
-- and aggregated so Qwen/the merchant can see what customers are asking for,
-- especially queries that match nothing in the catalog. Idempotent.
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS search_queries JSONB NOT NULL DEFAULT '{}';
