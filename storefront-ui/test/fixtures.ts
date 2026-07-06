import type { PublicStore, LayoutDSL } from '@/types/schemas'

export const fixtureDSL: LayoutDSL = {
  sections: [
    { type: 'hero', variant: 'editorial-stacked', props: {} },
    { type: 'product_grid', variant: 'featured-2col', props: {} },
  ],
  global_config: {
    nav_style: 'underline-tabs',
    product_card: 'hover-reveal-text',
    color_mode: 'auto',
    corner_radius: 'md',
    density: 'normal',
    add_to_cart: 'drawer-only',
    product_detail: 'gallery-split',
    cart_style: 'slide-panel',
  },
  custom_css: '',
}

export const fixtureStore: PublicStore = {
  store_name: 'Haree',
  slug: 'haree',
  logo_url: '',
  tagline: 'Quiet luxury',
  palette: { primary: '#0A0A0B', secondary: '#222', accent: '#6EE7B7', background: '#0A0A0B', text: '#fff' },
  typography: { display_font: 'Syne', body_font: 'Inter' },
  icons: { logo_mark: '<svg viewBox="0 0 64 64"><rect width="64" height="64"/></svg>', store_icon: '<svg/>' },
  layout: { layout_variant: 'standard' },
  products: [
    { id: 'p1', name: 'Face Wash', price: 24, available: true, category: 'care', image_url: null, description: 'd', compare_at_price: null, promo_label: null },
    { id: 'p2', name: 'Serum', price: 48, available: true, category: 'care', image_url: null, description: 'd', compare_at_price: null, promo_label: null },
  ],
  promos: [],
  categories: ['care'],
  brand_token: {
    store_name: 'Haree',
    tagline: 'Quiet luxury',
    colors: { primary: '#0A0A0B', accent: '#6EE7B7', background: '#0A0A0B', surface: '#111', text: '#fff', text_muted: '#999' },
    typography: { display_font: 'Syne', body_font: 'Inter', scale: 'editorial', letter_spacing: 'wide', weight: 'regular' },
    layout: { style: 'editorial', hero_type: 'split', product_grid: 'masonry', card_style: 'borderless', border_radius: '8px', spacing: 'balanced', category_style: 'underline-tab' },
    mood: 'refined',
    industry_hint: 'beauty',
    brand_voice: 'quiet',
    layout_dsl: fixtureDSL,
  },
}
