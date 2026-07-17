-- Qwen swarm roles: which named role (pricing_strategist, sales_rep,
-- inventory_overseer, store_curator) proposed this decision. NULL for any
-- row created before this migration — role_for_action_type() in
-- qwen_roles.py backfills a display label for those at read time instead of
-- a one-time UPDATE, since the mapping is derivable from action_type alone.
-- Idempotent.
ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS role VARCHAR;
