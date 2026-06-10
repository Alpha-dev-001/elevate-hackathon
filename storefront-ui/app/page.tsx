import Link from 'next/link'

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-8 p-8">
      <div className="text-center">
        <h1 className="text-5xl font-bold tracking-tight mb-2" style={{ fontFamily: 'var(--font-display)' }}>
          Elevate
        </h1>
        <p className="text-muted text-lg">Your store, alive.</p>
      </div>

      <div className="flex gap-4">
        <Link
          href="/terminal"
          className="px-6 py-3 rounded-lg border border-accent text-accent hover:bg-accent-dim transition-colors font-mono text-sm"
        >
          → Merchant Terminal
        </Link>
        <Link
          href="/storefront"
          className="px-6 py-3 rounded-lg border border-border text-text hover:border-accent transition-colors font-mono text-sm"
        >
          → Live Storefront
        </Link>
      </div>
    </main>
  )
}
