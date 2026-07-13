import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { OptionCard } from '@/components/terminal/OptionCard'
import type { AgentAction } from '@/types/schemas'

const dismissAction = vi.fn().mockResolvedValue({ action: {} })
const approveAction = vi.fn().mockResolvedValue({ action: {} })
vi.mock('@/lib/api', () => ({
  api: {
    dismissAction: (...a: any[]) => dismissAction(...a),
    approveAction: (...a: any[]) => approveAction(...a),
  },
}))

function makeAction(overrides: Partial<AgentAction> = {}): AgentAction {
  return {
    id: 'act_1',
    merchant_id: 'm1',
    promo_id: 'promo_1',
    action_type: 'duplicate_merge',
    trigger: 'Duplicate listings: 2 entries for "Slides"',
    title: 'Duplicate Cleanup: Slides',
    description: 'Merge 1 duplicate listing into one',
    estimated_gmv: 0,
    estimated_confidence: 0.75,
    payload: { keep_product_id: 'p1', remove_product_ids: ['p2'] },
    brand_check: 'Auto-generated via tool calling',
    reasoning: '',
    status: 'pending',
    created_at: Date.now(),
    ...overrides,
  }
}

describe('OptionCard — duplicate_merge dismiss confirm/undo', () => {
  beforeEach(() => {
    dismissAction.mockClear()
    approveAction.mockClear()
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows an undo snackbar instead of dismissing immediately', async () => {
    const onDismiss = vi.fn()
    const user = userEvent.setup({ delay: null })
    render(<OptionCard action={makeAction()} onApprove={vi.fn()} onDismiss={onDismiss} />)
    await user.click(screen.getByText('Dismiss'))

    expect(screen.getByText(/Duplicate merge dismissed/)).toBeTruthy()
    expect(dismissAction).not.toHaveBeenCalled()
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('Undo cancels the dismiss and restores the card', async () => {
    const onDismiss = vi.fn()
    const user = userEvent.setup({ delay: null })
    render(<OptionCard action={makeAction()} onApprove={vi.fn()} onDismiss={onDismiss} />)
    await user.click(screen.getByText('Dismiss'))
    await user.click(screen.getByText('Undo'))

    expect(screen.getByText('Dismiss')).toBeTruthy()
    vi.advanceTimersByTime(6000)
    expect(dismissAction).not.toHaveBeenCalled()
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('commits the real dismiss after the undo window elapses', async () => {
    const onDismiss = vi.fn()
    const user = userEvent.setup({ delay: null })
    render(<OptionCard action={makeAction()} onApprove={vi.fn()} onDismiss={onDismiss} />)
    await user.click(screen.getByText('Dismiss'))

    vi.advanceTimersByTime(5100)
    await waitFor(() => expect(dismissAction).toHaveBeenCalledWith('act_1'))
    await waitFor(() => expect(onDismiss).toHaveBeenCalledWith('act_1'))
  })

  it('other action types still dismiss instantly, no undo prompt', async () => {
    const onDismiss = vi.fn()
    const user = userEvent.setup({ delay: null })
    render(
      <OptionCard action={makeAction({ action_type: 'flash_sale' })} onApprove={vi.fn()} onDismiss={onDismiss} />,
    )
    await user.click(screen.getByText('Dismiss'))

    await waitFor(() => expect(dismissAction).toHaveBeenCalledWith('act_1'))
    await waitFor(() => expect(onDismiss).toHaveBeenCalledWith('act_1'))
    expect(screen.queryByText(/dismissed/i)).toBeNull()
  })

  it('an expired duplicate_merge card dismisses instantly too', async () => {
    const onDismiss = vi.fn()
    const user = userEvent.setup({ delay: null })
    const old = Date.now() - 10 * 60 * 1000 // 10 minutes ago — past the 5-minute TTL
    render(<OptionCard action={makeAction({ created_at: old })} onApprove={vi.fn()} onDismiss={onDismiss} />)
    await user.click(screen.getByText('Dismiss (expired)'))

    await waitFor(() => expect(dismissAction).toHaveBeenCalledWith('act_1'))
  })
})
