/**
 * Tiny WCAG contrast helpers for the storefront.
 *
 * Qwen picks a brand accent that's often a mid/light tone (e.g. #B7B7B7), which
 * is fine as a fill but unreadable as text on a light background. We keep the
 * brand accent for fills and derive a contrast-safe variant for accent-colored
 * TEXT, so prices and taglines stay legible without changing the brand.
 */

function hexToRgb(hex: string): [number, number, number] | null {
  const h = hex.replace('#', '').trim()
  if (h.length !== 6) return null
  const n = parseInt(h, 16)
  if (Number.isNaN(n)) return null
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function rgbToHex([r, g, b]: [number, number, number]): string {
  const c = (v: number) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')
  return `#${c(r)}${c(g)}${c(b)}`
}

function relLuminance([r, g, b]: [number, number, number]): number {
  const f = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

export function contrastRatio(fg: string, bg: string): number {
  const a = hexToRgb(fg)
  const b = hexToRgb(bg)
  if (!a || !b) return 1
  const la = relLuminance(a)
  const lb = relLuminance(b)
  const hi = Math.max(la, lb)
  const lo = Math.min(la, lb)
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * Return `fg` if it clears `min` contrast on `bg`; otherwise blend it toward
 * black or white (whichever the background calls for) just until it passes —
 * preserving as much of the original hue as possible.
 */
export function readableOn(fg: string, bg: string, min = 4.5): string {
  if (contrastRatio(fg, bg) >= min) return fg
  const rgb = hexToRgb(fg)
  const bgRgb = hexToRgb(bg)
  if (!rgb || !bgRgb) return contrastRatio('#000000', bg) >= contrastRatio('#ffffff', bg) ? '#000000' : '#ffffff'

  const target = relLuminance(bgRgb) > 0.4 ? 0 : 255 // dark text on light bg, light on dark
  for (let t = 0.15; t <= 1.0001; t += 0.15) {
    const blended: [number, number, number] = [
      rgb[0] + (target - rgb[0]) * t,
      rgb[1] + (target - rgb[1]) * t,
      rgb[2] + (target - rgb[2]) * t,
    ]
    const hex = rgbToHex(blended)
    if (contrastRatio(hex, bg) >= min) return hex
  }
  return target === 0 ? '#111111' : '#ffffff'
}
