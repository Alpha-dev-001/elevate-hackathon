import { Storefront } from '@/components/storefront/Storefront'

/**
 * Live store at /s/{slug}. Thin server wrapper that resolves the route param
 * (a Promise in Next 15) and hands the slug to the themed client storefront.
 */
export default async function StorePage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  return <Storefront slug={slug} />
}
