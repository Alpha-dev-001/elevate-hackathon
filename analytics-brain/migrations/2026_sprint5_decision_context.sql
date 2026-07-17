-- Persist what Qwen actually saw at decision time (catalog snapshot, prior-
-- outcome memory, discount ceiling) alongside the reasoning it produced, so
-- the Decision Trace page can show inputs and outputs together, not just
-- the outcome. Idempotent.
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS context_snapshot JSON NOT NULL DEFAULT '{}';
