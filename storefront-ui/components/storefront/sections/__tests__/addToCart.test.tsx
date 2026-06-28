import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SECTION_REGISTRY } from '@/lib/dslRegistry'
import '@/lib/registerVariants'
import { fixtureStore } from '@/test/fixtures'

const baseGlobal = fixtureStore.brand_token!.layout_dsl!.global_config

describe('DSL-driven inline add-to-cart', () => {
  it('drawer-only renders no inline add button', () => {
    const Grid = SECTION_REGISTRY.product_grid['masonry-4col']
    const { container } = render(
      <Grid store={fixtureStore} slug="haree" variant="masonry-4col"
            globalConfig={{ ...baseGlobal, add_to_cart: 'drawer-only' }} />,
    )
    expect(container.querySelector('[aria-label^="Add "]')).toBeFalsy()
  })

  it('card-always shows the button and fires onAddToCart, NOT onOpenProduct', async () => {
    const onAdd = vi.fn()
    const onOpen = vi.fn()
    const Grid = SECTION_REGISTRY.product_grid['masonry-4col']
    const { container } = render(
      <Grid store={fixtureStore} slug="haree" variant="masonry-4col"
            globalConfig={{ ...baseGlobal, add_to_cart: 'card-always' }}
            onAddToCart={onAdd} onOpenProduct={onOpen} />,
    )
    const btn = container.querySelector('[aria-label^="Add "]') as HTMLElement
    expect(btn).toBeTruthy()
    await userEvent.click(btn)
    expect(onAdd).toHaveBeenCalledWith(fixtureStore.products[0].id)
    expect(onOpen).not.toHaveBeenCalled()  // stopPropagation — add ≠ open drawer
  })

  it('preview disables the inline add button', () => {
    const Grid = SECTION_REGISTRY.product_grid['masonry-4col']
    const { container } = render(
      <Grid store={fixtureStore} slug="haree" variant="masonry-4col"
            globalConfig={{ ...baseGlobal, add_to_cart: 'card-always' }} preview />,
    )
    expect((container.querySelector('[aria-label^="Add "]') as HTMLButtonElement).disabled).toBe(true)
  })
})
