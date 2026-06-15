import Link from 'next/link'

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-8 p-8">
      <div className="text-center">
        <h1
          className="text-6xl font-bold tracking-tight mb-2"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          Elevate
        </h1>
        <p className="text-muted text-lg">Your store, alive.</p>
      </div>

      <Link
        href="/setup"
        className="px-8 py-3 rounded-lg bg-accent text-bg hover:opacity-90 transition-opacity
                   font-semibold text-sm accent-glow"
      >
        Build your store →
      </Link>
    </main>
  )
}
