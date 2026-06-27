/**
 * REST client for the analytics-brain backend.
 *
 * Every call sends the session cookie (credentials: 'include') — auth is an
 * httpOnly cookie, never a token in JS. Errors throw ApiError carrying the
 * status and the backend's `detail` (which may be a string or an object, e.g.
 * the 409 phase from GET /onboarding/brand).
 */
import type {
  Merchant,
  MerchantCreate,
  MerchantLogin,
  BrandPackage,
  PresignedUploadResponse,
  Product,
  PublicStore,
  Cart,
  Order,
  OrderCustomer,
  OrderStatus,
  Promo,
  PromoCreate,
  Constraints,
  CatalogReview,
  Violation,
  AgentAction,
} from '@/types/schemas'

export interface DashboardData {
  store_name: string
  total_gmv: number
  elevate_attributed_gmv: number
  elevate_fee: number
  actions: Array<{
    promo_id: string
    action_type: string
    title: string
    trigger: string
    estimated_gmv: number
    executed_at: number | null
    attributed_orders: number
    attributed_gmv: number
    fee: number
  }>
}

export interface ProductCreateInput {
  name: string
  price: number
  stock: number
  cost_price: number
  category?: string
  image_url?: string
}

export interface ProductCSVRowInput {
  name: string
  price: number
  stock: number
  image_url?: string
  category?: string
}

export interface ProductUpdateInput {
  name?: string
  price?: number
  cost_price?: number
  stock?: number
  category?: string
  image_url?: string
  is_active?: boolean
}

export interface ConstraintsUpdateInput {
  min_profit_margin_percent?: number
  max_discount_percent?: number
  min_price?: Record<string, number>
  accessibility_level?: 'AA' | 'AAA'
}

const enc = encodeURIComponent

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:9000'

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, message: string, detail: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      ...init,
    })
  } catch (e) {
    // Network-level failure (backend down, CORS, DNS) — make it legible.
    throw new ApiError(0, `Cannot reach the backend at ${API_BASE}`, String(e))
  }

  const raw = await res.text()
  const data = raw ? JSON.parse(raw) : null
  if (!res.ok) {
    const detail = (data && data.detail) ?? res.statusText
    const message =
      typeof detail === 'string' ? detail : 'Request failed'
    throw new ApiError(res.status, message, detail)
  }
  return data as T
}

export interface BrandResponse {
  brand_package: BrandPackage
  store_shell_url: string
}

export const api = {
  // ── Auth ────────────────────────────────────────────────────────────────
  signup: (body: MerchantCreate) =>
    req<Merchant>('/auth/signup', { method: 'POST', body: JSON.stringify(body) }),
  login: (body: MerchantLogin) =>
    req<Merchant>('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => req<{ status: string }>('/auth/logout', { method: 'POST' }),
  me: () => req<Merchant>('/auth/me'),

  // ── Upload ──────────────────────────────────────────────────────────────
  presignLogoUpload: (content_type: string) =>
    req<PresignedUploadResponse>('/api/upload/logo-url', {
      method: 'POST',
      body: JSON.stringify({ content_type }),
    }),

  // ── Onboarding ──────────────────────────────────────────────────────────
  onboardingStart: (logo_oss_url: string) =>
    req<{ status: string; merchant_id: string }>('/onboarding/start', {
      method: 'POST',
      body: JSON.stringify({ logo_oss_url }),
    }),
  getBrand: () => req<BrandResponse>('/onboarding/brand'),
  publish: () =>
    req<{ status: string; store_name: string; storefront_url: string }>(
      '/onboarding/publish',
      { method: 'POST' },
    ),

  // ── Products ────────────────────────────────────────────────────────────
  addProduct: (body: ProductCreateInput) =>
    req<Product>('/products', { method: 'POST', body: JSON.stringify(body) }),
  addProductsBatch: (products: ProductCSVRowInput[]) =>
    req<Product[]>('/products/batch', {
      method: 'POST',
      body: JSON.stringify({ products }),
    }),
  listProducts: () => req<Product[]>('/products'),
  updateProduct: (id: string, body: ProductUpdateInput) =>
    req<{ product: Product; violations: Violation[] }>(`/products/${enc(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteProduct: (id: string) =>
    req<null>(`/products/${enc(id)}`, { method: 'DELETE' }),

  // ── Public storefront ───────────────────────────────────────────────────
  getStore: (slug: string) => req<PublicStore>(`/api/store/${enc(slug)}`),

  // ── Public commerce: cart, checkout, order lookup (guest, slug-scoped) ────
  getCart: (slug: string, sessionId: string) =>
    req<Cart>(`/api/store/${enc(slug)}/cart?session_id=${enc(sessionId)}`),
  addToCart: (slug: string, sessionId: string, productId: string, qty = 1) =>
    req<Cart>(`/api/store/${enc(slug)}/cart/items`, {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, product_id: productId, qty }),
    }),
  setCartItem: (slug: string, sessionId: string, productId: string, qty: number) =>
    req<Cart>(`/api/store/${enc(slug)}/cart/items`, {
      method: 'PATCH',
      body: JSON.stringify({ session_id: sessionId, product_id: productId, qty }),
    }),
  clearCart: (slug: string, sessionId: string) =>
    req<Cart>(`/api/store/${enc(slug)}/cart?session_id=${enc(sessionId)}`, {
      method: 'DELETE',
    }),
  checkout: (slug: string, sessionId: string, customer: OrderCustomer) =>
    req<Order>(`/api/store/${enc(slug)}/checkout`, {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, customer }),
    }),
  getOrder: (slug: string, orderId: string, email: string) =>
    req<Order>(`/api/store/${enc(slug)}/order/${enc(orderId)}?email=${enc(email)}`),

  // ── Merchant ops: orders, promos, constraints, catalog review ─────────────
  merchantOrders: () => req<Order[]>('/merchant/orders'),
  updateOrderStatus: (id: string, status: OrderStatus) =>
    req<Order>(`/merchant/orders/${enc(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  listPromos: () => req<Promo[]>('/merchant/promos'),
  createPromo: (body: PromoCreate) =>
    req<{ promo: Promo; violations: Violation[] }>('/merchant/promos', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deletePromo: (id: string) =>
    req<null>(`/merchant/promos/${enc(id)}`, { method: 'DELETE' }),
  getConstraints: () => req<Constraints>('/merchant/constraints'),
  updateConstraints: (body: ConstraintsUpdateInput) =>
    req<Constraints>('/merchant/constraints', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  getCatalogReview: () => req<CatalogReview | null>('/merchant/catalog-review'),
  runCatalogReview: () =>
    req<CatalogReview>('/merchant/catalog-review', { method: 'POST' }),

  // ── Behavior events ─────────────────────────────────────────────────────
  ingestEvent: (slug: string, body: { event_type: string; product_id?: string; session_id: string; timestamp?: number }) =>
    req<{ ok: boolean }>(`/api/behavior/event/${enc(slug)}`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  simulateActivity: (slug: string) =>
    req<{ ok: boolean; scenario: string; events: number }>(`/api/behavior/simulate/${enc(slug)}`, {
      method: 'POST',
    }),

  // ── Agent actions ────────────────────────────────────────────────────────
  getPendingActions: (slug: string) =>
    req<{ actions: AgentAction[] }>(`/api/agent/actions/${enc(slug)}/pending`),
  approveAction: (actionId: string) =>
    req<{ action: AgentAction }>(`/api/agent/actions/${enc(actionId)}/approve`, {
      method: 'POST',
    }),
  dismissAction: (actionId: string) =>
    req<{ action: AgentAction }>(`/api/agent/actions/${enc(actionId)}/dismiss`, {
      method: 'POST',
    }),

  // ── Dashboard ────────────────────────────────────────────────────────────
  getDashboard: (slug: string) =>
    req<DashboardData>(`/api/dashboard/${enc(slug)}`),
}

export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:9000/ws'

/**
 * Upload a logo straight to OSS: ask the backend for a presigned PUT URL, then
 * PUT the file directly (the signed headers must be sent verbatim, and no
 * cookies — it's a cross-origin request to OSS, not our backend). Returns the
 * public URL to hand to onboardingStart.
 */
export async function uploadLogo(file: File): Promise<string> {
  const { upload_url, public_url, required_headers } = await api.presignLogoUpload(
    file.type || 'image/png',
  )
  let res: Response
  try {
    res = await fetch(upload_url, {
      method: 'PUT',
      body: file,
      headers: required_headers, // Content-Type + x-oss-object-acl, exactly as signed
    })
  } catch (e) {
    throw new ApiError(0, 'Could not reach OSS to upload the logo', String(e))
  }
  if (!res.ok) {
    throw new ApiError(res.status, 'OSS rejected the upload', await res.text())
  }
  return public_url
}
