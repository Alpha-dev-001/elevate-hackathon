import { describe, it, expect, vi } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { StoreBirth } from '@/components/storefront/StoreBirth'

class MockEventSource {
  listeners: Record<string, (e: any) => void> = {}
  url: string
  closed = false
  constructor(url: string) { this.url = url }
  addEventListener(type: string, cb: (e: any) => void) { this.listeners[type] = cb }
  close() { this.closed = true }
  emit(type: string, data: any) { this.listeners[type]?.({ data: JSON.stringify(data) }) }
}

describe('StoreBirth', () => {
  it('renders streamed steps and fires onComplete with payload', async () => {
    let es!: MockEventSource
    const factory = (url: string) => { es = new MockEventSource(url); return es as unknown as EventSource }
    const onComplete = vi.fn()

    render(<StoreBirth slug="haree" onComplete={onComplete} eventSourceFactory={factory} />)

    act(() => { es.emit('step', { step: 'composing_layout', label: 'qwen-max: Composing your store...', index: 4, total: 7 }) })
    await waitFor(() => expect(screen.getByText(/Composing your store/i)).toBeTruthy())

    const payload = { brand_token: { store_name: 'Haree' }, layout_dsl: { sections: [] } }
    act(() => { es.emit('complete', payload) })
    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(payload))
    expect(es.closed).toBe(true)
  })
})
