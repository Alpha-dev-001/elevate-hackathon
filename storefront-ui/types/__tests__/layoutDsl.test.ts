import { describe, it, expect } from 'vitest'
import { LayoutDSLSchema, BrandTokenSchema } from '@/types/schemas'

describe('LayoutDSLSchema', () => {
  it('parses a valid DSL and applies defaults', () => {
    const dsl = LayoutDSLSchema.parse({
      sections: [
        { type: 'hero', variant: 'editorial-stacked' },
        { type: 'product_grid', variant: 'featured-2col' },
      ],
      global_config: { nav_style: 'underline-tabs', product_card: 'hover-reveal-text' },
    })
    expect(dsl.global_config.color_mode).toBe('auto')
    expect(dsl.sections[0].props).toEqual({})
    expect(dsl.custom_css).toBe('')
  })

  it('rejects fewer than 2 sections', () => {
    expect(() =>
      LayoutDSLSchema.parse({
        sections: [{ type: 'hero', variant: 'minimal-wordmark' }],
        global_config: { nav_style: 'pill-nav', product_card: 'polaroid-card' },
      }),
    ).toThrow()
  })

  it('accepts brand_token with optional layout_dsl', () => {
    const bt = BrandTokenSchema.parse({
      store_name: 'X',
      tagline: 't',
      colors: { primary: '#000', accent: '#111', background: '#fff', surface: '#eee', text: '#000', text_muted: '#999' },
      typography: { display_font: 'Syne', body_font: 'Inter' },
      layout: { style: 'editorial', hero_type: 'split', product_grid: 'masonry', card_style: 'borderless', border_radius: '8px', spacing: 'balanced', category_style: 'pill' },
      mood: 'm',
      industry_hint: 'fashion',
      brand_voice: 'v',
    })
    expect(bt.layout_dsl ?? null).toBeNull()
  })
})
