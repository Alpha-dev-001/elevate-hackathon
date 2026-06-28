-- Sprint 3: memory loop + outcome attribution. Idempotent for existing dev DBs.
ALTER TABLE merchants     ADD COLUMN IF NOT EXISTS qwen_memory JSONB NOT NULL DEFAULT '{"entries": []}';
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS merchant_behavior VARCHAR(32);
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS trigger_description TEXT;
-- layout_dsl is stored inside brand_profiles.brand_tokens JSONB — no DDL needed.
