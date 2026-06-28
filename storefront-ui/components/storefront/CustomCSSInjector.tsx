'use client'
import { useEffect } from 'react'

/**
 * Injects the store's Qwen-generated scoped CSS into <head>. Sanitized
 * server-side; scoped to [data-store="{slug}"]. Cleans up on unmount.
 */
export function CustomCSSInjector({ css, slug }: { css: string; slug: string }) {
  useEffect(() => {
    if (!css) return
    const id = `store-css-${slug}`
    let el = document.getElementById(id) as HTMLStyleElement | null
    if (!el) {
      el = document.createElement('style')
      el.id = id
      document.head.appendChild(el)
    }
    el.textContent = css
    return () => el?.remove()
  }, [css, slug])
  return null
}
