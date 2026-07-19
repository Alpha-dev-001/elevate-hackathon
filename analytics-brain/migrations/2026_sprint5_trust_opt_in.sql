-- Earned trust unlocks the OPTION to auto-apply, not auto-apply itself —
-- the merchant explicitly opts in per (product, action_type) once eligible.
-- Defaults false: existing rows (all earned under the old silent-auto-apply
-- design) do NOT retroactively start auto-applying just because this
-- migration ran. Idempotent.
ALTER TABLE autopilot_trust ADD COLUMN IF NOT EXISTS auto_apply_enabled BOOLEAN NOT NULL DEFAULT FALSE;
