import { StoreBuilder } from '@/components/builder/StoreBuilder'

/**
 * Store Builder split-screen. Reached from the terminal ("Customize store").
 * ?slug={merchant_slug} selects the store. Merchant-only (gated in StoreBuilder).
 *
 * NOTE: lives at /builder — NOT /brand-review — because the onboarding flow
 * already owns /brand-review via the (onboarding) route group, and two pages
 * resolving to the same path is a hard Next.js build error.
 */
export default async function BuilderPage({
  searchParams,
}: {
  searchParams: Promise<{ slug?: string }>
}) {
  const { slug } = await searchParams
  if (!slug) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="font-mono text-sm text-neutral-400">Missing ?slug — open the builder from your terminal.</p>
      </main>
    )
  }
  return <StoreBuilder slug={slug} />
}
