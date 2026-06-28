import { StoreBuilder } from '@/components/builder/StoreBuilder'

/**
 * Store Builder split-screen. Reached from the terminal ("Customize Store") or
 * after StoreBirth during onboarding. ?slug={merchant_slug} selects the store.
 */
export default async function BrandReviewBuilderPage({
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
