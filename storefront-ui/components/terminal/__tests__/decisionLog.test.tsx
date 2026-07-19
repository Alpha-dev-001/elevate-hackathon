import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { DecisionLog } from '@/components/terminal/DecisionLog'

const getDecisions = vi.fn()
vi.mock('@/lib/api', () => ({
  api: { getDecisions: (...a: any[]) => getDecisions(...a) },
}))

let capturedOnEvent: ((event: string, payload: Record<string, unknown>) => void) | undefined
const wsClose = vi.fn()
vi.mock('@/lib/ws', () => ({
  connectTerminal: (_id: string, handlers: { onEvent?: (event: string, payload: Record<string, unknown>) => void }) => {
    capturedOnEvent = handlers.onEvent
    return { close: wsClose }
  },
}))

describe('DecisionLog', () => {
  beforeEach(() => {
    capturedOnEvent = undefined
    getDecisions.mockReset()
    wsClose.mockReset()
  })

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

  // Regression: this page previously had zero live-update path at all — a
  // decision resolved live (approve, dismiss, auto-apply) never showed up
  // here until a manual reload, since it only ever fetched once on mount.
  it('refetches and shows a newly resolved decision after a state_updated event, without a remount', async () => {
    getDecisions.mockResolvedValueOnce({
      decisions: [
        {
          id: 'act_1', action_type: 'flash_sale', title: 'Flash Sale: 15% off Slides',
          description: '24h flash sale', trigger: 'Velocity spike: 12 views in 30s',
          reasoning: '', status: 'pending', created_at: Date.now(),
        },
      ],
      total: 1,
    })
    render(<DecisionLog merchantId="m1" />)
    await waitFor(() => expect(screen.getByText('Flash Sale: 15% off Slides')).toBeTruthy())
    expect(screen.getByText(/pending/i)).toBeTruthy()

    getDecisions.mockResolvedValueOnce({
      decisions: [
        {
          id: 'act_1', action_type: 'flash_sale', title: 'Flash Sale: 15% off Slides',
          description: '24h flash sale', trigger: 'Velocity spike: 12 views in 30s',
          reasoning: '', status: 'executed', created_at: Date.now(), executed_at: Date.now(),
        },
      ],
      total: 1,
    })
    expect(capturedOnEvent).toBeTruthy()
    act(() => {
      capturedOnEvent!('state_updated', {})
    })

    await waitFor(() => expect(screen.getByText(/executed/i)).toBeTruthy())
  })

  it('does not open a WS connection when merchantId is not provided', () => {
    getDecisions.mockResolvedValueOnce({ decisions: [], total: 0 })
    render(<DecisionLog />)
    expect(capturedOnEvent).toBeUndefined()
  })
})
