import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StoreBuilder } from '@/components/builder/StoreBuilder'
import { useBuilderStore } from '@/lib/builderStore'
import { fixtureStore } from '@/test/fixtures'
import '@/lib/registerVariants'

const push = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))

const saveDsl = vi.fn().mockResolvedValue(fixtureStore.brand_token!.layout_dsl)
const publish = vi.fn().mockResolvedValue({ status: 'live' })
vi.mock('@/lib/api', () => ({
  api: {
    getStore: (..._a: any[]) => Promise.resolve(fixtureStore),
    getBrandGuards: () => Promise.resolve(null),
    saveDsl: (...a: any[]) => saveDsl(...a),
    regenerateDsl: vi.fn(),
    publish: () => publish(),
  },
  ApiError: class ApiError extends Error {},
}))
vi.mock('@/lib/cart', () => {
  const state = { open: false, cart: null, setOpen: vi.fn(), add: vi.fn(), init: vi.fn() }
  const useCart = (sel?: any) => (typeof sel === 'function' ? sel(state) : state)
  return { useCart, getSessionId: () => 'sess' }
})

beforeEach(() => { useBuilderStore.getState().reset(); push.mockClear(); saveDsl.mockClear() })

describe('StoreBuilder page', () => {
  it('shows Qwen Recommended badge, then Reset after a change, and publishes', async () => {
    render(<StoreBuilder slug="haree" />)
    await waitFor(() => expect(screen.getByText('✦ Qwen Recommended')).toBeTruthy())

    act(() => { useBuilderStore.getState().reorderSections(0, 1) })
    await waitFor(() => expect(screen.getByText(/Reset to Qwen/i)).toBeTruthy())

    await userEvent.click(screen.getByText(/Publish Store/i))
    await waitFor(() => expect(saveDsl).toHaveBeenCalled())
    await waitFor(() => expect(push).toHaveBeenCalledWith('/s/haree'))
  })
})
