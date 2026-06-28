import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DSLRenderer } from '@/components/storefront/DSLRenderer'
import { fixtureStore } from '@/test/fixtures'

// Cart's add() hits the API; stub it so the drawer test stays unit-level.
vi.mock('@/lib/cart', () => {
  const state = {
    open: false, cart: null, items: [],
    setOpen: vi.fn(), add: vi.fn().mockResolvedValue(true),
    remove: vi.fn(), init: vi.fn(), checkout: vi.fn(),
  }
  const useCart = (sel?: any) => (typeof sel === 'function' ? sel(state) : state)
  return { useCart, getSessionId: () => 'sess' }
})

describe('ProductDrawer', () => {
  beforeEach(() => { window.history.pushState(null, '', '/s/haree') })

  it('opens on product click and closes on close', async () => {
    render(<DSLRenderer store={fixtureStore} slug="haree" />)
    await userEvent.click(document.querySelector('[data-product]') as HTMLElement)
    await waitFor(() => expect(screen.getByTestId('product-drawer')).toBeTruthy())
    expect(window.location.search).toContain('p=')
    await userEvent.click(screen.getByLabelText('Close'))
    await waitFor(() => expect(screen.queryByTestId('product-drawer')).toBeFalsy())
  })
})
