import { ProductDetail } from '@/components/storefront/ProductDetail'

/**
 * Product detail at /s/{slug}/{productId}. Thin server wrapper resolving the
 * route params (Promises in Next 15) for the themed client detail view.
 */
export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string; productId: string }>
}) {
  const { slug, productId } = await params
  return <ProductDetail slug={slug} productId={productId} />
}
