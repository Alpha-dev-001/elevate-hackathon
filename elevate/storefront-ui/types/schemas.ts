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
  logo_url: z.string().url(),
  category: z.string(),
  brand_package: BrandPackageSchema.nullable(),
  onboarding_status: z.enum([
    'store_info', 'logo_upload', 'brand_review', 'products', 'live'
  ]),
  is_live: z.boolean(),
})

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
})

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
export type Product = z.infer<typeof ProductSchema>
export type SystemState = z.infer<typeof SystemStateSchema>
export type BrandWarning = z.infer<typeof BrandWarningSchema>
export type WSMessage = z.infer<typeof WSMessageSchema>
