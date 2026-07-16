import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { OptionCard } from '@/components/terminal/OptionCard'
import { api } from '@/lib/api'
import type { AgentAction } from '@/types/schemas'

vi.mock('@/lib/api', () => ({
  api: {
    approveAction: vi.fn().mockResolvedValue({ action: { status: 'executed' } }),
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

describe('OptionCard — discount override', () => {
  it('shows an input pre-filled with Qwen\'s proposed percent for a discount action', () => {
    render(<OptionCard action={makeAction()} onApprove={vi.fn()} onDismiss={vi.fn()} />)
    const input = screen.getByDisplayValue('20') as HTMLInputElement
    expect(input).toBeInTheDocument()
    expect(screen.getByText(/Qwen proposed 20%/)).toBeInTheDocument()
  })

  it('renders no override input for an action type with no discount', () => {
    render(<OptionCard action={makeAction({ action_type: 'layout_morph', payload: { hero_product_id: 'p1' } })}
      onApprove={vi.fn()} onDismiss={vi.fn()} />)
    expect(screen.queryByText(/Discount %/)).toBeNull()
  })

  it('approving with an unedited percent sends no override', async () => {
    render(<OptionCard action={makeAction()} onApprove={vi.fn()} onDismiss={vi.fn()} />)
    fireEvent.click(screen.getByText('Approve'))
    expect(api.approveAction).toHaveBeenCalledWith('act_1', undefined)
  })

  it('editing the percent and approving sends the override', async () => {
    render(<OptionCard action={makeAction()} onApprove={vi.fn()} onDismiss={vi.fn()} />)
    const input = screen.getByDisplayValue('20') as HTMLInputElement
    fireEvent.change(input, { target: { value: '35' } })
    fireEvent.click(screen.getByText('Approve'))
    expect(api.approveAction).toHaveBeenCalledWith('act_1', { discount_percent_override: 35 })
  })
})
