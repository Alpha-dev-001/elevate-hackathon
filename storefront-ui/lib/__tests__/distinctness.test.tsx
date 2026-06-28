import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { DSLRenderer } from '@/components/storefront/DSLRenderer'
import { fixtureStore, fixtureDSL } from '@/test/fixtures'
import type { LayoutDSL } from '@/types/schemas'

function signature(dsl: LayoutDSL) {
  const store = { ...fixtureStore, brand_token: { ...fixtureStore.brand_token!, layout_dsl: dsl } }
  const { container } = render(<DSLRenderer store={store as any} slug="x" />)
  return (
    [...container.querySelectorAll('[data-dsl-section]')]
      .map((n) => `${n.getAttribute('data-section-type')}:${n.getAttribute('data-variant')}`)
      .join('|') +
    '|' +
    (container.querySelector('[data-nav]')?.getAttribute('data-nav') ?? '')
  )
}

describe('rendered distinctness', () => {
  it('different DSLs produce different rendered structural signatures', () => {
    const a = signature(fixtureDSL)
    const b: LayoutDSL = {
      ...fixtureDSL,
      sections: [
        { type: 'banner', variant: 'announcement-bar', props: {} },
        { type: 'product_grid', variant: 'horizontal-scroll', props: {} },
        { type: 'story', variant: 'quote-callout', props: {} },
      ],
      global_config: { ...fixtureDSL.global_config, nav_style: 'sidebar-text', product_card: 'colored-bg-card' },
    }
    expect(signature(b)).not.toBe(a)
  })
})
