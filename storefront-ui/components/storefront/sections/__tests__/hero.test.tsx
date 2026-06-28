import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { SECTION_REGISTRY } from '@/lib/dslRegistry'
import '@/lib/registerVariants'
import { fixtureStore } from '@/test/fixtures'

const HERO_VARIANTS = ['full-bleed-image', 'editorial-stacked', 'minimal-wordmark', 'split-50-50']

describe('hero family', () => {
  it('registers all 4 hero variants', () => {
    for (const v of HERO_VARIANTS) expect(SECTION_REGISTRY.hero[v]).toBeTruthy()
  })

  it.each(HERO_VARIANTS)('%s renders without throwing', (variant) => {
    const Comp = SECTION_REGISTRY.hero[variant]
    const { container } = render(
      <Comp store={fixtureStore} slug="haree" variant={variant}
            globalConfig={fixtureStore.brand_token!.layout_dsl!.global_config} />,
    )
    expect(container.querySelector('[data-hero]')).toBeTruthy()
  })
})
