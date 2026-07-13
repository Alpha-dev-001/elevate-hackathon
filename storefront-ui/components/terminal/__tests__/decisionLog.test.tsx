import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { DecisionLog } from '@/components/terminal/DecisionLog'

const getDecisions = vi.fn()
vi.mock('@/lib/api', () => ({
  api: { getDecisions: (...a: any[]) => getDecisions(...a) },
}))

describe('DecisionLog', () => {
  it('renders each decision with its title, status, and trigger', async () => {
    getDecisions.mockResolvedValue({
      decisions: [
        {
          id: 'act_1', action_type: 'flash_sale', title: 'Flash Sale: 15% off Slides',
          description: '24h flash sale', trigger: 'Velocity spike: 12 views in 30s',
          reasoning: 'Views spiked, discounting to convert.', status: 'executed',
          created_at: Date.now(), approved_at: Date.now(), executed_at: Date.now(),
        },
      ],
      total: 1,
    })
    render(<DecisionLog />)
    await waitFor(() => expect(screen.getByText('Flash Sale: 15% off Slides')).toBeTruthy())
    expect(screen.getByText(/executed/i)).toBeTruthy()
    expect(screen.getByText(/Velocity spike/)).toBeTruthy()
  })

  it('shows an empty state when there are no decisions yet', async () => {
    getDecisions.mockResolvedValue({ decisions: [], total: 0 })
    render(<DecisionLog />)
    await waitFor(() => expect(getDecisions).toHaveBeenCalled())
    expect(screen.getByText(/no decisions yet/i)).toBeTruthy()
  })

  it('surfaces an error message instead of staying blank when the fetch fails', async () => {
    getDecisions.mockRejectedValue(new Error('network error'))
    render(<DecisionLog />)
    await waitFor(() => expect(screen.getByText(/could not load decision history/i)).toBeTruthy())
  })
})
