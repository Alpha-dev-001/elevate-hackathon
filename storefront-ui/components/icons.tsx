/**
 * Minimal monochrome line icons (feather-style). They inherit `currentColor` and
 * take a size, so they read as part of the UI type — not the mismatched color
 * emoji they replace (🛒 👤 ⚡ 📈 ✨) that looked out of place on the dark
 * terminal and the branded storefront.
 */
type IconProps = { size?: number; className?: string; style?: React.CSSProperties }

function base(size: number, className?: string, style?: React.CSSProperties) {
  return {
    width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const, className, style, 'aria-hidden': true,
  }
}

export function IconCart({ size = 18, className, style }: IconProps) {
  return (
    <svg {...base(size, className, style)}>
      <circle cx="9" cy="20" r="1.4" />
      <circle cx="18" cy="20" r="1.4" />
      <path d="M2 3h2.2l1.9 11.3a1.8 1.8 0 0 0 1.8 1.5h8.7a1.8 1.8 0 0 0 1.8-1.4L21 7H5.5" />
    </svg>
  )
}

export function IconUser({ size = 18, className, style }: IconProps) {
  return (
    <svg {...base(size, className, style)}>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}

export function IconBolt({ size = 18, className, style }: IconProps) {
  return (
    <svg {...base(size, className, style)}>
      <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" />
    </svg>
  )
}

export function IconTrend({ size = 18, className, style }: IconProps) {
  return (
    <svg {...base(size, className, style)}>
      <path d="M22 7 13.5 15.5l-4-4L2 19" />
      <path d="M16 7h6v6" />
    </svg>
  )
}

export function IconSpark({ size = 16, className, style }: IconProps) {
  return (
    <svg {...base(size, className, style)}>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
    </svg>
  )
}

export function IconSearch({ size = 18, className, style }: IconProps) {
  return (
    <svg {...base(size, className, style)}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  )
}

export function IconX({ size = 18, className, style }: IconProps) {
  return (
    <svg {...base(size, className, style)}>
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  )
}
