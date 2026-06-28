import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, act } from '@testing-library/react'
import { BuilderPreview } from '@/components/builder/BuilderPreview'
import { useBuilderStore } from '@/lib/builderStore'
import { fixtureStore, fixtureDSL } from '@/test/fixtures'
import '@/lib/registerVariants'

vi.mock('@/lib/cart', () => {
  const state = { open: false, cart: null, setOpen: vi.fn(), add: vi.fn(), init: vi.fn() }
  const useCart = (sel?: any) => (typeof sel === 'function' ? sel(state) : state)
  return { useCart, getSessionId: () => 'sess' }
})

const token = fixtureStore.brand_token!

beforeEach(() => {
  useBuilderStore.getState().reset()
  useBuilderStore.getState().setFromStore(fixtureDSL, token)
})

describe('BuilderPreview', () => {
  it('reflects draft section order without remounting the store wrapper', () => {
    const { container } = render(<BuilderPreview store={fixtureStore} />)
    const before = [...container.querySelectorAll('[data-dsl-section]')].map((n) => n.getAttribute('data-section-type'))
    expect(before[0]).toBe('hero')

    act(() => { useBuilderStore.getState().reorderSections(0, 1) })
    const after = [...container.querySelectorAll('[data-dsl-section]')].map((n) => n.getAttribute('data-section-type'))
    expect(after[0]).toBe('product_grid')
  })
})
