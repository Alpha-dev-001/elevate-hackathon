import type { PublicStore } from '@/types/schemas'

export function DSLFooter({ store }: { store: PublicStore }) {
  return (
    <footer
      data-dsl-footer
      className="text-center mt-16 py-10 text-xs font-mono"
      style={{ color: 'var(--s-text-subtle)' }}
    >
      {store.store_name} · Powered by Elevate
    </footer>
  )
}
