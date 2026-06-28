import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { CustomCSSInjector } from '@/components/storefront/CustomCSSInjector'

describe('CustomCSSInjector', () => {
  it('injects a scoped style element and cleans up on unmount', () => {
    const css = '[data-store="haree"] .product-card{opacity:.9}'
    const { unmount } = render(<CustomCSSInjector css={css} slug="haree" />)
    const el = document.getElementById('store-css-haree')
    expect(el).toBeTruthy()
    expect(el!.textContent).toContain('opacity:.9')
    unmount()
    expect(document.getElementById('store-css-haree')).toBeFalsy()
  })

  it('renders nothing for empty css', () => {
    render(<CustomCSSInjector css="" slug="empty-store" />)
    expect(document.getElementById('store-css-empty-store')).toBeFalsy()
  })
})
