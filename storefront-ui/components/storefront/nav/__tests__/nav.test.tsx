import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NAV_REGISTRY } from '@/lib/dslRegistry'
import '@/lib/registerVariants'
import { fixtureStore } from '@/test/fixtures'

const NAVS = ['underline-tabs', 'pill-nav', 'sidebar-text', 'sticky-tabs', 'minimal-text']

describe('nav family', () => {
  it('registers all 5 nav variants', () => {
    for (const v of NAVS) expect(NAV_REGISTRY[v]).toBeTruthy()
  })

  it.each(NAVS)('%s renders categories and fires onSelect', async (variant) => {
    const onSelect = vi.fn()
    const Comp = NAV_REGISTRY[variant]
    render(<Comp store={fixtureStore} activeCategory={null} onSelect={onSelect} />)
    const all = screen.getAllByText('All')[0]
    await userEvent.click(all)
    expect(onSelect).toHaveBeenCalledWith(null)
    const care = screen.getAllByText('care')[0]
    await userEvent.click(care)
    expect(onSelect).toHaveBeenCalledWith('care')
  })
})
