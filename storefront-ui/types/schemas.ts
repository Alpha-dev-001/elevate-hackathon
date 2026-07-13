import { z } from 'zod'

// ─── 1. The Eyes ──────────────────────────────────────────────────────────────

export const LogoAnalysisSchema = z.object({
  primary_colors: z.array(z.string()),
  secondary_colors: z.array(z.string()).default([]),
  mood: z.string(),
  style: z.string(),
  geometry_notes: z.string(),
})

// ─── 2. The Brain ─────────────────────────────────────────────────────────────

export const BrandPaletteSchema = z.object({
  primary: z.string(),
  secondary: z.string(),
  accent: z.string(),
  background: z.string(),
  text: z.string(),
})

export const BrandTypographySchema = z.object({
  display_font: z.string(),
  body_font: z.string(),
})

export const BrandIconSetSchema = z.object({
  logo_mark: z.string(),   // SVG string
  store_icon: z.string(),  // SVG string
})

export const GeneratedBrandSchema = z.object({
  store_name: z.string(),
  tagline: z.string(),
  palette: BrandPaletteSchema,
  typography: BrandTypographySchema,
  brand_voice_profile: z.string(),
  icons: BrandIconSetSchema,
  layout_variant: z.enum(['standard', 'promo_heavy', 'minimal']).default('standard'),
  suggested_categories: z.array(z.string()).default([]),
})

// ─── 3. The Interceptor ───────────────────────────────────────────────────────

export const BrandGuardRuleSchema = z.object({
  rule_id: z.string(),
  field: z.string(),        // which UI field triggers this warning
  description: z.string(),
  warning_message: z.string(),  // Qwen's own words — shown directly to merchant
})

export const BrandGuardRulesSchema = z.object({
  allowed_color_palette: z.array(z.string()),
  forbidden_combinations: z.array(z.string()).default([]),
  rules: z.array(BrandGuardRuleSchema),
})

// ─── 4. The Core Package ──────────────────────────────────────────────────────

export const BrandPackageSchema = z.object({
  analysis: LogoAnalysisSchema,
  brand: GeneratedBrandSchema,
  guards: BrandGuardRulesSchema,
})

// ─── 5. Merchant ──────────────────────────────────────────────────────────────

export const MerchantSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  store_name: z.string(),
  slug: z.string(),
  logo_url: z.string(),  // empty string until the logo upload step
  category: z.string(),
  brand_package: BrandPackageSchema.nullable(),
  onboarding_status: z.enum([
    'store_info', 'logo_upload', 'brand_review', 'products', 'live'
  ]),
  is_live: z.boolean(),
})

export const MerchantCreateSchema = z.object({
  email: z.string().email(),
  store_name: z.string().min(1),
  password: z.string().min(8).max(72),  // 72 = bcrypt input limit
  category: z.string().default('other'),
  description: z.string().default(''),
})

export const MerchantLoginSchema = z.object({
  email: z.string().email(),
  password: z.string(),
})

// ─── Per-brand customer (RBAC role=customer) ───────────────────────────────────
export const CustomerSchema = z.object({
  id: z.string(),
  merchant_id: z.string(),
  store_slug: z.string(),
  email: z.string().email(),
  name: z.string(),
  role: z.literal('customer').default('customer'),
})
export const CustomerCreateSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(72),
  name: z.string().min(1).max(120),
})
export const CustomerLoginSchema = z.object({
  email: z.string().email(),
  password: z.string(),
})
export type Customer = z.infer<typeof CustomerSchema>
export type CustomerCreate = z.infer<typeof CustomerCreateSchema>
export type CustomerLogin = z.infer<typeof CustomerLoginSchema>

// ─── 6. Product ───────────────────────────────────────────────────────────────

export const ProductSchema = z.object({
  id: z.string(),
  merchant_id: z.string(),
  name: z.string(),
  price: z.number().positive(),
  cost_price: z.number().positive(),
  stock: z.number().int().min(0),
  image_url: z.string().url().nullable().optional(),
  category: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  qwen_generated: z.boolean().default(false),
  is_pending: z.boolean().default(false),
  is_featured: z.boolean().default(false),
  featured_label: z.string().nullable().optional(),
})

// ─── 6b. Duplicate Detection ─────────────────────────────────────────────────

export const DuplicateGroupSchema = z.object({
  image_url: z.string(),
  product_ids: z.array(z.string()),
  names: z.array(z.string()),
  qwen_generated: z.boolean(),
  auto_resolved: z.boolean(),
})

export const DeduplicateReportSchema = z.object({
  auto_merged: z.array(DuplicateGroupSchema),
  needs_review: z.array(DuplicateGroupSchema),
  total_scanned: z.number().int(),
  total_duplicates: z.number().int(),
})

export type DuplicateGroup = z.infer<typeof DuplicateGroupSchema>
export type DeduplicateReport = z.infer<typeof DeduplicateReportSchema>

// ─── 6c. Catalog Audit (Qwen-powered review) ─────────────────────────────────

export const CatalogFindingSchema = z.object({
  product_id: z.string(),
  product_name: z.string(),
  issue_type: z.enum(['pricing_anomaly', 'missing_category', 'naming_issue', 'duplicate', 'description_quality']),
  severity: z.enum(['low', 'medium', 'high']),
  description: z.string(),
  suggested_fix: z.string(),
})

export const CatalogAuditReportSchema = z.object({
  findings: z.array(CatalogFindingSchema),
  catalog_score: z.number().int().min(0).max(100),
  summary: z.string(),
})

export type CatalogFinding = z.infer<typeof CatalogFindingSchema>
export type CatalogAuditReport = z.infer<typeof CatalogAuditReportSchema>

// ─── 7. System State ──────────────────────────────────────────────────────────
// Used for Zod gate before applying JSON patches — prevents silent desync

export const PromoSchema = z.object({
  id: z.string(),
  product_id: z.string(),
  discount_percent: z.number().min(0).max(100),
  label: z.string(),
  expires_at: z.number(),
  triggered_by: z.enum(['merchant', 'auto']),
})

// Order-level cart-recovery discount (mirrors RecoveryOffer in schemas.py).
// Discounts an existing cart's total only — never the browse grid.
export const RecoveryOfferSchema = z.object({
  percent: z.number(),
  label: z.string(),
  expires_at: z.number(),
  promo_id: z.string().default(''),
  triggered_by: z.enum(['merchant', 'auto']).default('auto'),
})

export const LayoutConfigSchema = z.object({
  hero_product_id: z.string().nullable().optional(),
  featured_category: z.string().nullable().optional(),
  banner_text: z.string().nullable().optional(),
  color_accent: z.string().nullable().optional(),
  layout_variant: z.enum(['standard', 'promo_heavy', 'minimal']).default('standard'),
})

export const SystemStateSchema = z.object({
  version: z.number().int(),
  last_updated: z.number(),
  products: z.record(ProductSchema),
  active_promos: z.record(PromoSchema).default({}),
  layout_config: LayoutConfigSchema.default({}),
  qr_campaigns: z.record(z.any()).default({}),
  recovery: RecoveryOfferSchema.nullable().optional(),
})

// ─── 8. WebSocket Messages ────────────────────────────────────────────────────

export const BrandWarningSchema = z.object({
  rule_id: z.string(),
  field: z.string(),
  severity: z.enum(['info', 'warning']),
  message: z.string(),
  proposed_value: z.any(),
})

export const WSMessageSchema = z.object({
  event: z.string(),
  payload: z.record(z.any()),
  merchant_id: z.string(),
  timestamp: z.number(),
})

// ─── 9. Onboarding API shapes ─────────────────────────────────────────────────

// POST /onboarding/start — the authenticated merchant hands us the OSS URL of
// their uploaded logo. Store info already lives on the merchant from signup.
export const LogoSubmitRequestSchema = z.object({
  logo_oss_url: z.string().url(),
})

// POST /api/upload/logo-url — presigned direct-to-OSS upload.
export const PresignedUploadRequestSchema = z.object({
  content_type: z.string(),
})

export const PresignedUploadResponseSchema = z.object({
  upload_url: z.string(),
  public_url: z.string(),
  object_key: z.string(),
  required_headers: z.record(z.string()),
})

// Payload of the `brand_ready` WS event (and GET /onboarding/brand body).
// Either the finished package, or an error if generation failed — the
// incubation screen branches on which is present.
export const BrandReadyPayloadSchema = z.union([
  z.object({
    brand_package: BrandPackageSchema,
    store_shell_url: z.string(),
  }),
  z.object({
    error: z.string(),
  }),
])

// ─── BrandToken (spec-aligned layout DNA) ─────────────────────────────────

export const BrandColorsSchema = z.object({
  primary: z.string(),
  accent: z.string(),
  background: z.string(),
  surface: z.string(),
  text: z.string(),
  text_muted: z.string(),
})

export const BrandTypographyTokenSchema = z.object({
  display_font: z.string(),
  body_font: z.string(),
  scale: z.enum(['compact', 'balanced', 'editorial']).default('balanced'),
  letter_spacing: z.enum(['tight', 'normal', 'wide']).default('normal'),
  weight: z.enum(['light', 'regular', 'medium', 'bold']).default('regular'),
})

export const BrandLayoutTokenSchema = z.object({
  style: z.enum(['editorial', 'bold-grid', 'minimal-dark', 'warm-craft']),
  hero_type: z.enum(['full-bleed', 'text-forward', 'split', 'texture-bg']),
  product_grid: z.enum(['2col-featured', '3col-equal', 'masonry']),
  card_style: z.enum(['borderless', 'outlined', 'elevated', 'colored-bg']),
  border_radius: z.enum(['2px', '8px', '16px', '24px']),
  spacing: z.enum(['compact', 'balanced', 'generous']),
  category_style: z.enum(['pill', 'underline-tab', 'minimal-text']),
})

// ─── Sprint 3: LayoutDSL (mirrors schemas.py exactly) ──────────────────────────
export const LayoutSectionSchema = z.object({
  type: z.enum(['hero', 'product_grid', 'banner', 'story']),
  variant: z.string(),
  props: z.record(z.any()).default({}),
})

export const LayoutGlobalConfigSchema = z.object({
  nav_style: z.enum(['underline-tabs', 'pill-nav', 'sidebar-text', 'sticky-tabs', 'minimal-text']),
  product_card: z.enum([
    'hover-reveal-text', 'colored-bg-card', 'editorial-horizontal',
    'borderless-floating', 'polaroid-card', 'image-below-text',
  ]),
  color_mode: z.enum(['light', 'dark', 'auto']).default('auto'),
  corner_radius: z.enum(['none', 'sm', 'md', 'lg', 'full']).default('md'),
  density: z.enum(['sparse', 'normal', 'dense']).default('normal'),
  add_to_cart: z.enum(['drawer-only', 'card-hover', 'card-always', 'none']).default('drawer-only'),
  product_detail: z.enum(['gallery-split', 'editorial-stacked', 'minimal-centered']).default('gallery-split'),
  cart_style: z.enum(['slide-panel', 'full-sheet']).default('slide-panel'),
})

export const LayoutDSLSchema = z.object({
  sections: z.array(LayoutSectionSchema).min(2).max(5),
  global_config: LayoutGlobalConfigSchema,
  custom_css: z.string().default(''),
})

export const BrandTokenSchema = z.object({
  store_name: z.string(),
  tagline: z.string(),
  colors: BrandColorsSchema,
  typography: BrandTypographyTokenSchema,
  layout: BrandLayoutTokenSchema,
  mood: z.string(),
  industry_hint: z.string(),
  brand_voice: z.string(),
  layout_dsl: LayoutDSLSchema.nullable().optional(),
})

// ─── 10. Public storefront payload ────────────────────────────────────────────

export const PublicProductSchema = z.object({
  id: z.string(),
  price: z.number(),                               // effective price (after promo)
  name: z.string(),
  compare_at_price: z.number().nullable().optional(),  // original price when discounted
  promo_label: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  image_url: z.string().nullable().optional(),
  category: z.string().nullable().optional(),
  available: z.boolean(),
  is_featured: z.boolean().default(false),
  featured_label: z.string().nullable().optional(),
})

export const PublicStoreSchema = z.object({
  store_name: z.string(),
  slug: z.string(),
  merchant_id: z.string().default(''),  // storefront WebSocket room id (live state pushes)
  logo_url: z.string().default(''),   // real uploaded logo; '' → generated SVG mark
  tagline: z.string(),
  palette: BrandPaletteSchema,
  typography: BrandTypographySchema,
  icons: BrandIconSetSchema,
  layout: LayoutConfigSchema,
  products: z.array(PublicProductSchema),
  promos: z.array(PromoSchema).default([]),
  recovery: RecoveryOfferSchema.nullable().optional(),
  categories: z.array(z.string()).default([]),
  brand_token: BrandTokenSchema.nullable().optional(),
})

// ─── 11. Sprint 2 — Commerce: cart, checkout, orders ──────────────────────────

export const OrderStatusSchema = z.enum([
  'pending', 'paid', 'shipped', 'delivered', 'cancelled',
])

export const CartItemSchema = z.object({
  product_id: z.string(),
  name: z.string(),
  unit_price: z.number(),     // snapshot taken at add-time
  qty: z.number().int().positive(),
  image_url: z.string().nullable().optional(),
  line_total: z.number(),
})

export const CartSchema = z.object({
  session_id: z.string(),
  merchant_id: z.string(),
  items: z.array(CartItemSchema).default([]),
  subtotal: z.number().default(0),
  item_count: z.number().int().default(0),
  // Order-level recovery discount overlaid by the backend at read time.
  discount_percent: z.number().default(0),
  discount_label: z.string().nullable().optional(),
  discount_expires_at: z.number().nullable().optional(),
  discount_amount: z.number().default(0),
  total: z.number().default(0),
  updated_at: z.number(),
})

export const OrderItemSchema = z.object({
  product_id: z.string(),
  name: z.string(),
  unit_price: z.number(),
  qty: z.number().int().positive(),
  line_total: z.number(),
})

export const OrderCustomerSchema = z.object({
  name: z.string().min(1).max(120),
  email: z.string().email(),
  note: z.string().default(''),
})

export const OrderSchema = z.object({
  id: z.string(),
  merchant_id: z.string(),
  session_id: z.string(),
  items: z.array(OrderItemSchema),
  subtotal: z.number(),
  total: z.number(),
  status: OrderStatusSchema,
  customer_name: z.string(),
  customer_email: z.string(),
  promo_applied: z.string().nullable().optional(),
  created_at: z.number(),
})

// ─── 12. Sprint 2 — Merchant pricing controls + catalog review ────────────────

export const PromoCreateSchema = z.object({
  product_id: z.string(),
  discount_percent: z.number().positive().max(100),
  label: z.string().min(1).max(80),
  duration_minutes: z.number().int().positive().max(43200).default(1440),
})

export const ConstraintsSchema = z.object({
  min_profit_margin_percent: z.number().min(0).max(100).optional(),
  max_discount_percent: z.number().min(0).max(100).optional(),
  min_price: z.record(z.number()).optional(),
  accessibility_level: z.enum(['AA', 'AAA']).optional(),
})

export const PricingFlagSchema = z.object({
  product_id: z.string(),
  name: z.string(),
  severity: z.enum(['low', 'medium', 'high']),
  issue: z.string(),
  suggestion: z.string(),
})

export const CatalogReviewSchema = z.object({
  flags: z.array(PricingFlagSchema).default([]),
  summary: z.string(),
  reviewed_count: z.number().int(),
  generated_at: z.number(),
})

// A single violation surfaced when the interceptor clamps/blocks a merchant action.
export const ViolationSchema = z.object({
  rule: z.string(),
  severity: z.enum(['warning', 'blocked']),
  message: z.string(),
  original_value: z.any().nullable().optional(),
  clamped_value: z.any().nullable().optional(),
})

// ─── AgentAction ─────────────────────────────────────────────────────────────

export const AgentActionTypeSchema = z.enum([
  'flash_sale', 'layout_morph', 'scarcity_price', 'recovery_offer', 'copy_rewrite', 'duplicate_merge',
])

export const AgentActionStatusSchema = z.enum([
  'pending', 'approved', 'dismissed', 'executed',
])

export const AgentActionSchema = z.object({
  id: z.string(),
  merchant_id: z.string(),
  promo_id: z.string(),
  action_type: AgentActionTypeSchema,
  trigger: z.string(),
  title: z.string(),
  description: z.string(),
  estimated_gmv: z.number(),
  estimated_confidence: z.number(),
  payload: z.record(z.any()),
  brand_check: z.string(),
  reasoning: z.string().default(''),
  status: AgentActionStatusSchema,
  created_at: z.number(),
  approved_at: z.number().nullable().optional(),
  executed_at: z.number().nullable().optional(),
})

// ─── Inferred Types ───────────────────────────────────────────────────────────

export type LogoAnalysis = z.infer<typeof LogoAnalysisSchema>
export type BrandPalette = z.infer<typeof BrandPaletteSchema>
export type BrandTypography = z.infer<typeof BrandTypographySchema>
export type BrandIconSet = z.infer<typeof BrandIconSetSchema>
export type GeneratedBrand = z.infer<typeof GeneratedBrandSchema>
export type BrandGuardRule = z.infer<typeof BrandGuardRuleSchema>
export type BrandGuardRules = z.infer<typeof BrandGuardRulesSchema>
export type BrandPackage = z.infer<typeof BrandPackageSchema>
export type Merchant = z.infer<typeof MerchantSchema>
export type MerchantCreate = z.infer<typeof MerchantCreateSchema>
export type MerchantLogin = z.infer<typeof MerchantLoginSchema>
export type Product = z.infer<typeof ProductSchema>
export type SystemState = z.infer<typeof SystemStateSchema>
export type Promo = z.infer<typeof PromoSchema>
export type RecoveryOffer = z.infer<typeof RecoveryOfferSchema>
export type BrandWarning = z.infer<typeof BrandWarningSchema>
export type WSMessage = z.infer<typeof WSMessageSchema>
export type LogoSubmitRequest = z.infer<typeof LogoSubmitRequestSchema>
export type BrandReadyPayload = z.infer<typeof BrandReadyPayloadSchema>
export type PresignedUploadRequest = z.infer<typeof PresignedUploadRequestSchema>
export type PresignedUploadResponse = z.infer<typeof PresignedUploadResponseSchema>
export type PublicProduct = z.infer<typeof PublicProductSchema>
export type PublicStore = z.infer<typeof PublicStoreSchema>
export type OrderStatus = z.infer<typeof OrderStatusSchema>
export type CartItem = z.infer<typeof CartItemSchema>
export type Cart = z.infer<typeof CartSchema>
export type OrderItem = z.infer<typeof OrderItemSchema>
export type OrderCustomer = z.infer<typeof OrderCustomerSchema>
export type Order = z.infer<typeof OrderSchema>
export type PromoCreate = z.infer<typeof PromoCreateSchema>
export type Constraints = z.infer<typeof ConstraintsSchema>
export type PricingFlag = z.infer<typeof PricingFlagSchema>
export type CatalogReview = z.infer<typeof CatalogReviewSchema>
export type Violation = z.infer<typeof ViolationSchema>
export type BrandColors = z.infer<typeof BrandColorsSchema>
export type BrandTypographyToken = z.infer<typeof BrandTypographyTokenSchema>
export type BrandLayoutToken = z.infer<typeof BrandLayoutTokenSchema>
export type BrandToken = z.infer<typeof BrandTokenSchema>
export type LayoutSection = z.infer<typeof LayoutSectionSchema>
export type LayoutGlobalConfig = z.infer<typeof LayoutGlobalConfigSchema>
export type LayoutDSL = z.infer<typeof LayoutDSLSchema>
export type AgentActionType = z.infer<typeof AgentActionTypeSchema>
export type AgentActionStatus = z.infer<typeof AgentActionStatusSchema>
export type AgentAction = z.infer<typeof AgentActionSchema>
