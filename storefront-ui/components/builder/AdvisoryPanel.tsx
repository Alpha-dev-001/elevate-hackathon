'use client'
import type { BrandGuardRule } from '@/types/schemas'

/**
 * Brand-guard advisory. Pure local render of pre-generated copy — ZERO Qwen
 * calls at interaction time (the warning_message was authored at brand-creation).
 * Never blocks; only advises.
 */
export function AdvisoryPanel({ rule, mode }: { rule: BrandGuardRule; mode: 'conversational' | 'structured' }) {
  return (
    <div data-testid="advisory" role="status"
         className="mt-2 rounded-lg p-3 text-xs leading-relaxed"
         style={{ background: 'rgba(255,209,102,0.12)', color: '#FFD166', border: '1px solid rgba(255,209,102,0.3)' }}>
      {mode === 'conversational' ? (
        <p>{rule.warning_message}</p>
      ) : (
        <div className="font-mono">
          <p><span className="opacity-60">rule:</span> {rule.rule_id}</p>
          <p><span className="opacity-60">field:</span> {rule.field}</p>
          <p className="mt-1">{rule.warning_message}</p>
        </div>
      )}
      <p className="mt-2 opacity-70">Brand guard noted. Your choice.</p>
    </div>
  )
}
