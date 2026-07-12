'use client'
import { useState } from 'react'
import type { NavProps } from '@/lib/dslRegistry'

export function SidebarTextNav({ store, activeCategory, onSelect, preview }: NavProps) {
  const [open, setOpen] = useState(false)
  const items: (string | null)[] = [null, ...store.categories]
  const list = (
    <ul className="flex flex-col gap-3 text-sm uppercase tracking-wide">
      {items.map((c) => (
        <li key={c ?? 'all'}>
          <button onClick={() => { onSelect(c); setOpen(false) }}
                  className="nav-link"
                  style={{ color: activeCategory === c ? 'var(--s-accent)' : 'var(--s-text-muted)' }}>
            {c ?? 'All'}
          </button>
        </li>
      ))}
    </ul>
  )
  // Live store: fixed full-height rail. Builder preview: absolute within the
  // store container so it never escapes the pane and covers the builder controls.
  // (The container — the [data-store] div — is position:relative, and scrolls.)
  const railClass = preview
    ? 'nav-links hidden md:block absolute left-0 top-0 h-full w-44 px-6 py-10 overflow-y-auto'
    : 'nav-links hidden md:block fixed left-0 top-0 h-full w-44 px-6 py-10 overflow-y-auto'
  return (
    <>
      <button className="md:hidden px-5 py-3 text-sm" aria-label="Menu" onClick={() => setOpen((o) => !o)}>☰ Menu</button>
      <nav className={railClass} style={{ background: 'var(--s-bg)' }}>
        {list}
      </nav>
      {open && (
        <nav className="nav-links md:hidden px-6 py-4" style={{ background: 'var(--s-bg)' }}>{list}</nav>
      )}
    </>
  )
}
