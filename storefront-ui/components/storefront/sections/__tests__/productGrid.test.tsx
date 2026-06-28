import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SECTION_REGISTRY } from '@/lib/dslRegistry'
import '@/lib/registerVariants'
import { fixtureStore } from '@/test/fixtures'

const GRID_VARIANTS = ['masonry-4col', 'featured-2col', 'horizontal-scroll', 'single-spotlight']

describe('product-grid family', () => {
  it('registers all 4 grid variants', () => {
    for (const v of GRID_VARIANTS) expect(SECTION_REGISTRY.product_grid[v]).toBeTruthy()
  })

  it.each(GRID_VARIANTS)('%s renders grid + products even with empty card registry', (variant) => {
    const Comp = SECTION_REGISTRY.product_grid[variant]
    const { container } = render(
      <Comp store={fixtureStore} slug="haree" variant={variant}
            globalConfig={fixtureStore.brand_token!.layout_dsl!.global_config} />,
    )
    expect(container.querySelector('[data-grid]')).toBeTruthy()
    expect(container.querySelectorAll('[data-product]').length).toBeGreaterThan(0)
  })

  it('clicking a product calls onOpenProduct', async () => {
    const onOpen = vi.fn()
    const Comp = SECTION_REGISTRY.product_grid['featured-2col']
    const { container } = render(
      <Comp store={fixtureStore} slug="haree" variant="featured-2col"
            globalConfig={fixtureStore.brand_token!.layout_dsl!.global_config} onOpenProduct={onOpen} />,
    )
    await userEvent.click(container.querySelector('[data-product]') as HTMLElement)
    expect(onOpen).toHaveBeenCalled()
  })
})
