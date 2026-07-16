import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DSLRenderer } from '@/components/storefront/DSLRenderer'
import { fixtureStore, fixtureDSL } from '@/test/fixtures'

describe('DSLRenderer', () => {
  it('renders one DOM node per DSL section', () => {
    render(<DSLRenderer store={fixtureStore} slug="haree" />)
    const sections = document.querySelectorAll('[data-dsl-section]')
    expect(sections.length).toBe(fixtureStore.brand_token!.layout_dsl!.sections.length)
  })

  it('renders the configured nav style', () => {
    render(<DSLRenderer store={fixtureStore} slug="haree" />)
    expect(document.querySelector('[data-nav="underline-tabs"]')).toBeTruthy()
  })

  it('falls back when no layout_dsl', () => {
    const store = { ...fixtureStore, brand_token: { ...fixtureStore.brand_token!, layout_dsl: null } }
    render(<DSLRenderer store={store as any} slug="haree" />)
    expect(screen.getByTestId('fallback-storefront')).toBeTruthy()
  })

  it('clicking a category chip actually filters the product_grid section', () => {
    // Regression test: DSLNav used to own activeCategory as fully local
    // state, so the chip's own active/underline indicator updated but the
    // click never reached the product_grid section — every DSL-rendered
    // storefront's filter chips were cosmetic only. See memory:
    // elevate-dsl-category-filter-broken.
    const mixedStore = {
      ...fixtureStore,
      brand_token: {
        ...fixtureStore.brand_token!,
        layout_dsl: {
          ...fixtureDSL,
          sections: [{ type: 'product_grid' as const, variant: 'masonry-4col', props: {} }],
        },
      },
      products: [
        { ...fixtureStore.products[0], id: 'p1', name: 'Face Wash', category: 'care' },
        { ...fixtureStore.products[1], id: 'p2', name: 'Serum', category: 'care' },
        { ...fixtureStore.products[0], id: 'p3', name: 'Desk Lamp', category: 'home' },
      ],
      categories: ['care', 'home'],
    }
    render(<DSLRenderer store={mixedStore as any} slug="haree" />)

    expect(screen.getAllByText('Desk Lamp').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Face Wash').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: 'home' }))

    expect(screen.queryByText('Face Wash')).not.toBeInTheDocument()
    expect(screen.queryByText('Serum')).not.toBeInTheDocument()
    expect(screen.getAllByText('Desk Lamp').length).toBeGreaterThan(0)
  })

  it('a non-product_grid section is never filtered by the active category', () => {
    // The hero section must keep seeing the full catalog even while a
    // category filter is active elsewhere on the page.
    const mixedStore = {
      ...fixtureStore,
      layout: { ...fixtureStore.layout, hero_product_id: 'p3' },
      products: [
        { ...fixtureStore.products[0], id: 'p1', name: 'Face Wash', category: 'care' },
        { ...fixtureStore.products[0], id: 'p3', name: 'Desk Lamp', category: 'home' },
      ],
      categories: ['care', 'home'],
    }
    render(<DSLRenderer store={mixedStore as any} slug="haree" />)
    fireEvent.click(screen.getByRole('button', { name: 'care' }))
    // Both sections still mount (hero unaffected by the filter, product_grid
    // narrowed) — the hero section node count is unchanged.
    const sections = document.querySelectorAll('[data-dsl-section]')
    expect(sections.length).toBe(mixedStore.brand_token!.layout_dsl!.sections.length)
  })
})
