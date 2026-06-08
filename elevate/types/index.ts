// ─── Telemetry ────────────────────────────────────────────────────────────────

export interface CustomerEvent {
  sessionId: string
  productId: string
  eventType: 'view' | 'hover' | 'cart_add' | 'cart_remove' | 'purchase' | 'abandon'
  timestamp: number
  metadata?: Record<string, unknown>
}

export interface TelemetrySnapshot {
  capturedAt: number
  activeSessionCount: number
  productVelocity: Record<string, number>   // productId → views/min
  transactionRate: number                    // purchases/min
  abandonRate: number
  hotProducts: string[]                      // top 5 by velocity
  anomalies: Anomaly[]
}

export interface Anomaly {
  type: 'velocity_spike' | 'high_abandon' | 'low_stock_surge' | 'dead_product'
  productId?: string
  severity: 'low' | 'medium' | 'high'
  detectedAt: number
  context: Record<string, unknown>
}

// ─── Business Profile (Subconscious Interceptor) ──────────────────────────────

export interface BusinessProfile {
  merchantId: string
  storeName: string
  constraints: {
    minProfitMarginPercent: number    // e.g. 15 — Qwen cannot go below this
    maxDiscountPercent: number        // e.g. 40 — hard ceiling on any promo
    minPrice: Record<string, number>  // productId → floor price
    brandColors: string[]             // enforced in layout mutations
    accessibilityLevel: 'AA' | 'AAA' // WCAG compliance floor
  }
  products: Product[]
}

export interface Product {
  id: string
  name: string
  price: number
  costPrice: number
  stock: number
  category: string
  imageUrl?: string
}

// ─── Qwen Decision Engine ─────────────────────────────────────────────────────

export interface QwenDecisionRequest {
  snapshot: TelemetrySnapshot
  profile: BusinessProfile
  currentState: SystemState
}

export interface QwenDecision {
  reasoning: string                  // Qwen's internal justification
  proposedActions: ProposedAction[]
  urgency: 'routine' | 'moderate' | 'urgent'
  estimatedImpact: string
}

export interface ProposedAction {
  id: string
  type: 'price_adjust' | 'promo_trigger' | 'layout_shift' | 'qr_campaign' | 'alert'
  label: string                      // human-readable option card title
  description: string
  patch: JsonPatch[]                 // the actual delta to apply
  riskLevel: 'safe' | 'moderate' | 'review'
  estimatedRevenueDelta?: number
}

// ─── Delta Engine ─────────────────────────────────────────────────────────────

export interface JsonPatch {
  op: 'add' | 'remove' | 'replace' | 'move' | 'copy' | 'test'
  path: string
  value?: unknown
  from?: string
}

export interface DeltaExecution {
  actionId: string
  patches: JsonPatch[]
  executedAt: number
  executedBy: 'merchant' | 'auto'
  previousState: Partial<SystemState>
  rollbackAvailable: boolean
}

// ─── System State ─────────────────────────────────────────────────────────────

export interface SystemState {
  version: number
  lastUpdated: number
  products: Record<string, Product>
  activePromos: Record<string, Promo>
  layoutConfig: LayoutConfig
  qrCampaigns: Record<string, QRCampaign>
}

export interface Promo {
  id: string
  productId: string
  discountPercent: number
  label: string
  expiresAt: number
  triggeredBy: 'merchant' | 'auto'
}

export interface LayoutConfig {
  heroProductId?: string
  featuredCategory?: string
  bannerText?: string
  colorAccent?: string
  layoutVariant: 'standard' | 'promo_heavy' | 'minimal'
}

export interface QRCampaign {
  id: string
  productId: string
  promoId?: string
  scanCount: number
  createdAt: number
  expiresAt?: number
  deepLinkUrl: string
}

// ─── Terminal UI ──────────────────────────────────────────────────────────────

export interface OptionCard {
  action: ProposedAction
  status: 'pending' | 'approved' | 'rejected' | 'staged'
  stagedPreview?: Partial<SystemState>
}

export interface MerchantCommand {
  raw: string
  intent: 'review_actions' | 'approve' | 'reject' | 'stage_preview' | 'rollback' | 'status'
  targetActionId?: string
}
