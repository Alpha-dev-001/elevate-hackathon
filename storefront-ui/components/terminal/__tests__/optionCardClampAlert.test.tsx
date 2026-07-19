import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { OptionCard } from '@/components/terminal/OptionCard'
import { api } from '@/lib/api'
import type { AgentAction } from '@/types/schemas'

vi.mock('@/lib/api', () => ({
  api: {
    approveAction: vi.fn(),
    dismissAction: vi.fn().mockResolvedValue({ action: {} }),
  },
}))

function makeAction(overrides: Partial<AgentAction> = {}): AgentAction {
  return {
    id: 'act_1', merchant_id: 'm1', promo_id: 'promo_1',
    action_type: 'flash_sale', trigger: 'spike', title: 'Flash Sale: 20% off Widget',
    description: 'desc', estimated_gmv: 100, estimated_confidence: 0.75,
    payload: { product_id: 'p1', discount_percent: 20 },
    brand_check: 'Aligned with warm voice', constraint_check: '', reasoning: '',
    status: 'pending', created_at: Date.now(),
    ...overrides,
  }
}

// Regression for a real bug: the interceptor correctly clamped an
// over-ceiling discount on approval, but nothing told the merchant — the
// card just approved and vanished at what looked like the requested
// number. Fixed by threading the clamp message up to a page-level alert
// (onClamped), since the card itself unmounts right after.
describe('OptionCard — clamp alert on approval', () => {
  beforeEach(() => {
    vi.mocked(api.approveAction).mockReset()
  })

  it('calls onClamped when the approve response carries a constraint_check', async () => {
    vi.mocked(api.approveAction).mockResolvedValue({
      action: { ...makeAction(), status: 'executed', constraint_check: '60% exceeds your 40% discount ceiling. Clamped to 40%.' },
    })
    const onClamped = vi.fn()
    const onApprove = vi.fn()
    render(<OptionCard action={makeAction()} onApprove={onApprove} onDismiss={vi.fn()} onClamped={onClamped} />)

    fireEvent.click(screen.getByText('Approve'))

    await waitFor(() => expect(onApprove).toHaveBeenCalledWith('act_1'))
    expect(onClamped).toHaveBeenCalledWith('60% exceeds your 40% discount ceiling. Clamped to 40%.')
  })

  it('does not call onClamped when approval succeeds with no constraint_check', async () => {
    vi.mocked(api.approveAction).mockResolvedValue({
      action: { ...makeAction(), status: 'executed', constraint_check: '' },
    })
    const onClamped = vi.fn()
    const onApprove = vi.fn()
    render(<OptionCard action={makeAction()} onApprove={onApprove} onDismiss={vi.fn()} onClamped={onClamped} />)

    fireEvent.click(screen.getByText('Approve'))

    await waitFor(() => expect(onApprove).toHaveBeenCalledWith('act_1'))
    expect(onClamped).not.toHaveBeenCalled()
  })

  it('does not call onClamped or onApprove when blocked at execution', async () => {
    vi.mocked(api.approveAction).mockResolvedValue({
      action: { ...makeAction(), status: 'blocked_at_execution' },
    })
    const onClamped = vi.fn()
    const onApprove = vi.fn()
    render(<OptionCard action={makeAction()} onApprove={onApprove} onDismiss={vi.fn()} onClamped={onClamped} />)

    fireEvent.click(screen.getByText('Approve'))

    await waitFor(() => expect(screen.getByText(/Blocked at approval/)).toBeInTheDocument())
    expect(onClamped).not.toHaveBeenCalled()
    expect(onApprove).not.toHaveBeenCalled()
  })
})
