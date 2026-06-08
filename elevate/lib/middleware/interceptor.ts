import type { ProposedAction, BusinessProfile, JsonPatch } from '@/types'

// ─── The Subconscious Interceptor ─────────────────────────────────────────────
// Every proposed action passes through here before reaching the merchant.
// This layer is immutable — Qwen cannot override it.

export interface ValidationResult {
  valid: boolean
  action: ProposedAction
  violations: Violation[]
  clampedPatches?: JsonPatch[]  // auto-corrected patches if clamping was applied
}

export interface Violation {
  rule: string
  severity: 'warning' | 'blocked'
  message: string
  originalValue?: unknown
  clampedValue?: unknown
}

export function validateAction(
  action: ProposedAction,
  profile: BusinessProfile
): ValidationResult {
  const violations: Violation[] = []
  let clampedPatches = [...action.patch]

  for (const patch of action.patch) {
    // ── Price floor check ────────────────────────────────────────────────────
    if (patch.path.includes('/price') && patch.op === 'replace') {
      const productId = extractProductId(patch.path)
      const product = profile.products.find(p => p.id === productId)

      if (product && typeof patch.value === 'number') {
        const minPrice = profile.constraints.minPrice[productId]
        const minMarginPrice = product.costPrice * (1 + profile.constraints.minProfitMarginPercent / 100)
        const floor = Math.max(minPrice || 0, minMarginPrice)

        if (patch.value < floor) {
          violations.push({
            rule: 'min_profit_margin',
            severity: 'warning',
            message: `Price $${patch.value} violates ${profile.constraints.minProfitMarginPercent}% minimum margin. Clamping to $${floor.toFixed(2)}.`,
            originalValue: patch.value,
            clampedValue: parseFloat(floor.toFixed(2)),
          })
          // Auto-clamp rather than block — merchant sees the adjustment
          clampedPatches = clampedPatches.map(p =>
            p.path === patch.path ? { ...p, value: parseFloat(floor.toFixed(2)) } : p
          )
        }
      }
    }

    // ── Discount ceiling check ────────────────────────────────────────────────
    if (patch.path.includes('/discountPercent') && patch.op === 'replace') {
      if (typeof patch.value === 'number' && patch.value > profile.constraints.maxDiscountPercent) {
        violations.push({
          rule: 'max_discount',
          severity: 'warning',
          message: `Discount ${patch.value}% exceeds maximum ${profile.constraints.maxDiscountPercent}%. Clamping.`,
          originalValue: patch.value,
          clampedValue: profile.constraints.maxDiscountPercent,
        })
        clampedPatches = clampedPatches.map(p =>
          p.path === patch.path
            ? { ...p, value: profile.constraints.maxDiscountPercent }
            : p
        )
      }
    }

    // ── Brand color enforcement ───────────────────────────────────────────────
    if (patch.path.includes('/colorAccent') && typeof patch.value === 'string') {
      if (
        profile.constraints.brandColors.length > 0 &&
        !profile.constraints.brandColors.includes(patch.value)
      ) {
        violations.push({
          rule: 'brand_color',
          severity: 'warning',
          message: `Color ${patch.value} is outside brand palette. Clamping to nearest brand color.`,
          originalValue: patch.value,
          clampedValue: profile.constraints.brandColors[0],
        })
        clampedPatches = clampedPatches.map(p =>
          p.path === patch.path
            ? { ...p, value: profile.constraints.brandColors[0] }
            : p
        )
      }
    }
  }

  const blocked = violations.some(v => v.severity === 'blocked')

  return {
    valid: !blocked,
    action: {
      ...action,
      patch: clampedPatches,
      // Escalate risk level if violations were found
      riskLevel: violations.length > 0 ? 'moderate' : action.riskLevel,
    },
    violations,
    clampedPatches: violations.length > 0 ? clampedPatches : undefined,
  }
}

// ─── Batch validation ─────────────────────────────────────────────────────────

export function validateDecision(
  actions: ProposedAction[],
  profile: BusinessProfile
): ValidationResult[] {
  return actions.map(action => validateAction(action, profile))
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function extractProductId(path: string): string {
  // e.g. /products/prod_123/price → prod_123
  const parts = path.split('/')
  const productIndex = parts.indexOf('products')
  return productIndex >= 0 ? parts[productIndex + 1] : ''
}
