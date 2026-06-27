'use client'

import type { BrandToken } from '@/types/schemas'

interface CategoryNavProps {
  categories: string[]
  active: string | null
  onSelect: (cat: string | null) => void
  brandToken: BrandToken
}

/**
 * Three category navigation styles, driven by brandToken.layout.category_style:
 *   pill          — rounded chip buttons with accent fill on active
 *   underline-tab — flat tabs with sliding underline active state
 *   minimal-text  — plain monospace text links, uppercase
 */
export function CategoryNav({ categories, active, onSelect, brandToken }: CategoryNavProps) {
  if (categories.length === 0) return null
  const { layout, colors } = brandToken
  const style = layout.category_style

  if (style === 'pill') {
    return (
      <div className="flex flex-wrap gap-2 mb-8">
        {['All', ...categories].map((c) => {
          const isActive = c === 'All' ? active === null : active === c
          return (
            <button
              key={c}
              onClick={() => onSelect(c === 'All' ? null : c)}
              className="px-4 py-1.5 rounded-full text-sm font-medium transition-colors"
              style={
                isActive
                  ? { background: colors.accent, color: colors.background }
                  : {
                      background: colors.surface,
                      color: colors.text_muted,
                      border: `1px solid ${colors.text_muted}44`,
                    }
              }
            >
              {c}
            </button>
          )
        })}
      </div>
    )
  }

  if (style === 'underline-tab') {
    return (
      <div
        className="flex gap-6 mb-8 overflow-x-auto border-b"
        style={{ borderColor: `${colors.text}22` }}
      >
        {['All', ...categories].map((c) => {
          const isActive = c === 'All' ? active === null : active === c
          return (
            <button
              key={c}
              onClick={() => onSelect(c === 'All' ? null : c)}
              className="pb-3 text-sm font-medium transition-colors relative shrink-0"
              style={{ color: isActive ? colors.text : colors.text_muted }}
            >
              {c}
              {isActive && (
                <span
                  className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full"
                  style={{ background: colors.accent }}
                />
              )}
            </button>
          )
        })}
      </div>
    )
  }

  // minimal-text
  return (
    <div className="flex flex-wrap gap-5 mb-10">
      {['All', ...categories].map((c) => {
        const isActive = c === 'All' ? active === null : active === c
        return (
          <button
            key={c}
            onClick={() => onSelect(c === 'All' ? null : c)}
            className="text-[11px] uppercase tracking-[0.2em] font-mono transition-colors"
            style={{ color: isActive ? colors.text : colors.text_muted }}
          >
            {c}
          </button>
        )
      })}
    </div>
  )
}
