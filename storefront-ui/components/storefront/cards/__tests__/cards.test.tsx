import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CARD_REGISTRY } from '@/lib/dslRegistry'
import '@/lib/registerVariants'
import { fixtureStore } from '@/test/fixtures'

const CARD_VARIANTS = [
  'hover-reveal-text', 'colored-bg-card', 'editorial-horizontal',
  'borderless-floating', 'polaroid-card', 'image-below-text',
]
const product = fixtureStore.products[0]

describe('product-card family', () => {
  it('registers all 6 card variants', () => {
    for (const v of CARD_VARIANTS) expect(CARD_REGISTRY[v]).toBeTruthy()
  })

  it.each(CARD_VARIANTS)('%s renders and fires onOpen', async (variant) => {
    const onOpen = vi.fn()
    const Comp = CARD_REGISTRY[variant]
    const { container } = render(
      <Comp product={product} slug="haree" cornerRadius="md" onOpen={onOpen} />,
    )
    expect(container.querySelector('[data-card]')).toBeTruthy()
    await userEvent.click(container.querySelector('[data-product]') as HTMLElement)
    expect(onOpen).toHaveBeenCalledWith(product.id)
  })
})
