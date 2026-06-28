import { CustomerAccount } from '@/components/storefront/CustomerAccount'

/**
 * Per-brand customer sign-in / register at /s/{slug}/account. Themed by the
 * store's brand — the customer never sees Elevate, only this store.
 */
export default async function AccountPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  return <CustomerAccount slug={slug} />
}
