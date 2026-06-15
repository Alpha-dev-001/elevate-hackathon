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
} from '@/types/schemas'

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
