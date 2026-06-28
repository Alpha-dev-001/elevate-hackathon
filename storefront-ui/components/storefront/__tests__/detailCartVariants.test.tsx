import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProductDrawer } from '@/components/storefront/ProductDrawer'
import { Cart } from '@/components/storefront/Cart'
import { fixtureStore } from '@/test/fixtures'

vi.mock('@/lib/cart', () => {
  const state = {
    open: true, cart: { items: [], subtotal: 0 }, busy: false, error: null, slug: 'haree',
    setOpen: vi.fn(), add: vi.fn(), setQty: vi.fn(), remove: vi.fn(),
  }
  const useCart: any = (sel?: any) => (typeof sel === 'function' ? sel(state) : state)
  useCart.setState = vi.fn()
  return { useCart, getSessionId: () => 'sess' }
})

const product = fixtureStore.products[0]

describe('product detail variants', () => {
  it.each(['gallery-split', 'editorial-stacked', 'minimal-centered'] as const)(
    '%s renders with its data-detail-variant',
    (variant) => {
      render(<ProductDrawer product={product} store={fixtureStore} onClose={() => {}} variant={variant} />)
      const el = screen.getByTestId('product-drawer')
      expect(el.getAttribute('data-detail-variant')).toBe(variant)
    },
  )
})

describe('cart variants', () => {
  it.each(['slide-panel', 'full-sheet'] as const)('%s renders with its data-cart-style', (variant) => {
    const { container } = render(<Cart variant={variant} />)
    expect(container.querySelector(`[data-cart-style="${variant}"]`)).toBeTruthy()
  })
})
