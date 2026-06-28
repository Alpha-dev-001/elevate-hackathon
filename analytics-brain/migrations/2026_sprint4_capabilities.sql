-- Sprint 4: track unmet point-and-edit intents so Qwen can propose NEW config
-- dimensions when the same gap recurs. Idempotent.
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS capability_requests JSONB NOT NULL DEFAULT '{}';
