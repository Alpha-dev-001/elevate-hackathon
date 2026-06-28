import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DSLRenderer } from '@/components/storefront/DSLRenderer'
import { fixtureStore } from '@/test/fixtures'

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
})
