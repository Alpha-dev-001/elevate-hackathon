import { Storefront } from '@/components/storefront/Storefront'

/**
 * Live store at /s/{slug}. Thin server wrapper that resolves the route param
 * (a Promise in Next 15) and hands the slug to the themed client storefront.
 * ?p={productId} deep-links straight into the product drawer.
 */
export default async function StorePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>
  searchParams: Promise<{ p?: string }>
}) {
  const { slug } = await params
  const { p } = await searchParams
  return <Storefront slug={slug} initialProductId={p ?? null} />
}
