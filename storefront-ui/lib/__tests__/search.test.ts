import { describe, it, expect } from 'vitest'
import { matchesSearch } from '@/lib/search'
import type { PublicProduct } from '@/types/schemas'

function product(overrides: Partial<PublicProduct> = {}): PublicProduct {
  return {
    id: 'p1', price: 10, name: 'Winter Boots', available: true, is_featured: false,
    description: 'Warm and waterproof', category: 'Footwear',
    ...overrides,
  }
}

describe('matchesSearch', () => {
  it('empty query matches everything', () => {
    expect(matchesSearch(product(), '')).toBe(true)
    expect(matchesSearch(product(), '   ')).toBe(true)
  })

  it('matches on name, case-insensitively', () => {
    expect(matchesSearch(product({ name: 'Winter Boots' }), 'boots')).toBe(true)
    expect(matchesSearch(product({ name: 'Winter Boots' }), 'BOOTS')).toBe(true)
  })

  it('matches on description', () => {
    expect(matchesSearch(product({ description: 'Warm and waterproof' }), 'waterproof')).toBe(true)
  })

  it('matches on category', () => {
    expect(matchesSearch(product({ category: 'Footwear' }), 'footwear')).toBe(true)
  })

  it('does not match unrelated text', () => {
    expect(matchesSearch(product({ name: 'Winter Boots', description: 'Warm', category: 'Footwear' }), 'sunglasses')).toBe(false)
  })

  it('null description/category do not crash', () => {
    expect(matchesSearch(product({ description: null, category: null }), 'boots')).toBe(true)
    expect(matchesSearch(product({ description: null, category: null }), 'nothing')).toBe(false)
  })
})
