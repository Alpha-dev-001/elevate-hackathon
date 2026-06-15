'use client'

import { motion } from 'framer-motion'
import type { BrandPackage } from '@/types/schemas'

const ease = [0.4, 0, 0.2, 1] as const
const rise = {
  hidden: { opacity: 0, y: 16 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease },
  }),
}

/**
 * Step 3 — the reveal. Everything Qwen authored, surfaced like rising water.
 * SVG marks are injected raw because the backend already sanitizes them
 * (strips script/handlers/external refs) before they ever leave the server.
 */
export function BrandPreview({ pkg }: { pkg: BrandPackage }) {
  const { brand, guards } = pkg
  const swatches: [string, string][] = [
    ['Primary', brand.palette.primary],
    ['Secondary', brand.palette.secondary],
    ['Accent', brand.palette.accent],
    ['Background', brand.palette.background],
    ['Text', brand.palette.text],
  ]

  let i = 0
  const Section = ({ children }: { children: React.ReactNode }) => (
    <motion.div variants={rise} custom={i++} initial="hidden" animate="show">
      {children}
    </motion.div>
  )

  return (
    <div className="w-full max-w-2xl flex flex-col gap-6">
      <Section>
        <div className="flex items-center gap-4">
          <div
            className="w-16 h-16 shrink-0 [&>svg]:w-full [&>svg]:h-full"
            dangerouslySetInnerHTML={{ __html: brand.icons.logo_mark }}
          />
          <div>
            <h1
              className="text-4xl font-bold tracking-tight"
              style={{ fontFamily: 'var(--font-display)' }}
            >
              {brand.store_name}
            </h1>
            <p className="text-accent text-sm mt-1">{brand.tagline}</p>
          </div>
        </div>
      </Section>

      <Section>
        <div className="card p-5">
          <p className="font-mono text-[11px] text-muted uppercase tracking-widest mb-3">
            Palette
          </p>
          <div className="flex gap-3 flex-wrap">
            {swatches.map(([label, hex]) => (
              <div key={label} className="flex flex-col items-center gap-1.5">
                <div
                  className="w-12 h-12 rounded-lg border border-border"
                  style={{ background: hex }}
                />
                <span className="text-[10px] text-muted font-mono">{label}</span>
                <span className="text-[10px] text-text font-mono">{hex}</span>
              </div>
            ))}
          </div>
        </div>
      </Section>

      <Section>
        <div className="card p-5">
          <p className="font-mono text-[11px] text-muted uppercase tracking-widest mb-3">
            Typography &amp; voice
          </p>
          <div className="flex gap-6 mb-4">
            <div>
              <p className="text-[10px] text-muted font-mono">Display</p>
              <p className="text-lg text-text">{brand.typography.display_font}</p>
            </div>
            <div>
              <p className="text-[10px] text-muted font-mono">Body</p>
              <p className="text-lg text-text">{brand.typography.body_font}</p>
            </div>
          </div>
          <p className="text-sm text-text leading-relaxed">
            {brand.brand_voice_profile}
          </p>
          {brand.suggested_categories.length > 0 && (
            <div className="flex gap-2 flex-wrap mt-4">
              {brand.suggested_categories.map((c) => (
                <span
                  key={c}
                  className="text-xs font-mono px-2.5 py-1 rounded-full border border-border text-muted"
                >
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>
      </Section>

      <Section>
        <div className="card p-5 border-accent-dim">
          <p className="font-mono text-[11px] text-accent uppercase tracking-widest mb-3">
            What Qwen will protect
          </p>
          <div className="flex flex-col gap-3">
            {guards.rules.map((r) => (
              <div key={r.rule_id} className="border-l-2 border-accent pl-3">
                <p className="text-[10px] text-muted font-mono uppercase mb-0.5">
                  {r.field}
                </p>
                <p className="text-sm text-text leading-relaxed italic">
                  “{r.warning_message}”
                </p>
              </div>
            ))}
          </div>
        </div>
      </Section>
    </div>
  )
}
