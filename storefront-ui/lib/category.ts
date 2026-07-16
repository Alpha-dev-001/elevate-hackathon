/**
 * Category comparison is case/whitespace-insensitive everywhere on the
 * storefront — "Shoes", "shoes", and " Shoes " must all be treated as the
 * same category for filter chips, active-chip matching, and "more like
 * this" lookups. The display string (whatever casing was first seen) is
 * left untouched; only comparisons go through this.
 */
export function sameCategory(a?: string | null, b?: string | null): boolean {
  const na = (a ?? '').trim().toLowerCase()
  const nb = (b ?? '').trim().toLowerCase()
  return na !== '' && na === nb
}
