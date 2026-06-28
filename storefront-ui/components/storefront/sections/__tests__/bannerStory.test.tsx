import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SECTION_REGISTRY } from '@/lib/dslRegistry'
import '@/lib/registerVariants'
import { fixtureStore } from '@/test/fixtures'

const BANNERS = ['scroll-ticker', 'static-strip', 'announcement-bar']
const STORIES = ['full-bleed-text', 'split-image-story', 'quote-callout']
const gc = fixtureStore.brand_token!.layout_dsl!.global_config

describe('banner + story families', () => {
  it('registers 3 banners + 3 stories', () => {
    for (const v of BANNERS) expect(SECTION_REGISTRY.banner[v]).toBeTruthy()
    for (const v of STORIES) expect(SECTION_REGISTRY.story[v]).toBeTruthy()
  })

  it.each(BANNERS)('banner %s renders', (variant) => {
    const Comp = SECTION_REGISTRY.banner[variant]
    const { container } = render(<Comp store={fixtureStore} slug="haree" variant={variant} globalConfig={gc} />)
    expect(container.querySelector('[data-banner]')).toBeTruthy()
  })

  it.each(STORIES)('story %s renders', (variant) => {
    const Comp = SECTION_REGISTRY.story[variant]
    const { container } = render(<Comp store={fixtureStore} slug="haree" variant={variant} globalConfig={gc} />)
    expect(container.querySelector('[data-story]')).toBeTruthy()
  })

  it('announcement-bar dismiss removes it', async () => {
    const Comp = SECTION_REGISTRY.banner['announcement-bar']
    const { container } = render(<Comp store={fixtureStore} slug="haree-dismiss-test" variant="announcement-bar" globalConfig={gc} />)
    expect(container.querySelector('[data-banner]')).toBeTruthy()
    await userEvent.click(container.querySelector('[aria-label="Dismiss"]') as HTMLElement)
    expect(container.querySelector('[data-banner]')).toBeFalsy()
  })
})
