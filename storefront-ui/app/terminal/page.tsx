'use client'

import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { AnimatePresence } from 'framer-motion'
import { api, ApiError, type DashboardData, type Capability, type EligibleTrust } from '@/lib/api'
import { connectTerminal } from '@/lib/ws'
import type { AgentAction, Merchant, Product } from '@/types/schemas'
import { StoreSnapshot } from '@/components/terminal/StoreSnapshot'
import { DecisionFeed } from '@/components/terminal/DecisionFeed'
import { AttributionDashboard } from '@/components/terminal/AttributionDashboard'
import { CapabilityProposals } from '@/components/terminal/CapabilityProposals'
import { EarnedTrustPanel } from '@/components/terminal/EarnedTrustPanel'
import { ConstraintsSettings } from '@/components/terminal/ConstraintsSettings'
import { PendingProductCard, type PendingProduct } from '@/components/terminal/PendingProductCard'
import { SearchDemandInsights } from '@/components/terminal/SearchDemandInsights'

export default function TerminalPage() {
  const router = useRouter()

  const [merchant, setMerchant] = useState<Merchant | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [pendingActions, setPendingActions] = useState<AgentAction[]>([])
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [dashboardLoading, setDashboardLoading] = useState(false)
  const [reviewState, setReviewState] = useState<'idle' | 'sending' | 'found' | 'clean' | 'error'>('idle')
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [memoryCount, setMemoryCount] = useState<number | null>(null)
  const [lastTokens, setLastTokens] = useState<number | null>(null)
  const [capabilities, setCapabilities] = useState<Capability[]>([])
  const [qwenFallback, setQwenFallback] = useState<{ message: string; type: string } | null>(null)
  const [clampAlert, setClampAlert] = useState<string | null>(null)

  // A card that lands, gets clamped, and vanishes in the same few seconds
  // is easy to miss if you're not staring at that exact spot. Page-level
  // and manually dismissed (no auto-timeout) — the merchant should have to
  // actively clear it, not have it disappear whether or not they saw it.
  const handleClamped = useCallback((msg: string) => setClampAlert(msg), [])
  const [pendingProducts, setPendingProducts] = useState<PendingProduct[]>([])
  const [eligibleTrust, setEligibleTrust] = useState<EligibleTrust[]>([])
  const [autoExecutedAlert, setAutoExecutedAlert] = useState<{ title: string; reasoning: string } | null>(null)

  // ── Auth gate ──────────────────────────────────────────────────────────────

  useEffect(() => {
    api
      .me()
      .then(setMerchant)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          router.push('/setup')
        }
      })
      .finally(() => setAuthLoading(false))
  }, [router])

  // ── Data fetchers ──────────────────────────────────────────────────────────

  const fetchActions = useCallback(async (slug: string) => {
    try {
      const { actions } = await api.getPendingActions(slug)
      setPendingActions((prev) => {
        const existingIds = new Set(prev.map((a) => a.id))
        const newOnes = actions.filter((a) => !existingIds.has(a.id))
        if (newOnes.length === 0) return prev
        return [...newOnes, ...prev]
      })
    } catch {
      // ignore poll errors — next tick will retry
    }
  }, [])

  const fetchDashboard = useCallback(async (slug: string) => {
    setDashboardLoading(true)
    try {
      const data = await api.getDashboard(slug)
      setDashboard(data)
      // Persist memory count from API so it survives page refresh
      if (typeof data.memory_count === 'number') setMemoryCount(data.memory_count)
    } catch {
      // keep stale data rather than crashing
    } finally {
      setDashboardLoading(false)
    }
  }, [])

  const fetchCapabilities = useCallback(async (slug: string) => {
    try {
      const { capabilities } = await api.getCapabilities(slug)
      setCapabilities(capabilities)
    } catch {
      // non-critical surface — leave whatever we had
    }
  }, [])

  const fetchEligibleTrust = useCallback(async () => {
    try {
      const { eligible } = await api.listAutopilotTrust()
      setEligibleTrust(eligible)
    } catch {
      // non-critical surface — leave whatever we had
    }
  }, [])

  // ── Subscriptions ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (!merchant) return
    const { slug, id } = merchant

    // Initial fetch — one-time hydration on mount, not polling. Everything
    // after this point arrives over the WS subscription below.
    fetchActions(slug)
    fetchDashboard(slug)
    fetchCapabilities(slug)
    fetchEligibleTrust()
    api.listPendingProducts().then(setPendingProducts).catch(() => {})

    // WS subscription
    const conn = connectTerminal(id, {
      onOpen: () => setWsStatus('connected'),
      onClose: () => setWsStatus('disconnected'),
      onQwenFallback: (payload) => {
        setQwenFallback({ message: payload.message, type: payload.type })
        // Auto-dismiss after 8 seconds — the merchant sees the transparency
        // message, then it fades. Not a permanent error banner.
        window.setTimeout(() => setQwenFallback(null), 8000)
      },
      onEvent: (event, payload) => {
        if (event === 'agent_action' && payload.action) {
          const incoming = payload.action as AgentAction
          if (typeof payload.memory_count === 'number') setMemoryCount(payload.memory_count)
          if (typeof payload.estimated_tokens === 'number') setLastTokens(payload.estimated_tokens)
          setPendingActions((prev) => {
            if (prev.some((a) => a.id === incoming.id)) return prev
            return [incoming, ...prev]
          })
        }
        if (event === 'action_expired' && payload.action_id) {
          // Backend auto-dismissed a stale action (signal expired past TTL)
          setPendingActions((prev) => prev.filter((a) => a.id !== payload.action_id))
        }
        if (event === 'state_updated') {
          fetchDashboard(slug)
          // Streaks shift on every approve/dismiss/auto-apply outcome —
          // cheap to refetch, and this list is exactly what tells the
          // merchant whether a product just became toggle-eligible.
          fetchEligibleTrust()
        }
        if (event === 'action_auto_executed' && payload.action) {
          const auto = payload.action as { title: string; reasoning: string }
          setAutoExecutedAlert({ title: auto.title, reasoning: auto.reasoning })
        }
        if (event === 'products_pending' && Array.isArray(payload.products)) {
          const incoming = payload.products as PendingProduct[]
          setPendingProducts((prev) => {
            const existingIds = new Set(prev.map((p) => p.id))
            const newOnes = incoming.filter((p) => !existingIds.has(p.id))
            return newOnes.length ? [...newOnes, ...prev] : prev
          })
        }
        if (event === 'capability_updated' && Array.isArray(payload.capabilities)) {
          // The only source for capability gaps — they originate in the
          // builder's point-and-edit flow, a different page than this one,
          // so there's no local mutation to react to; this push is it.
          setCapabilities(payload.capabilities as Capability[])
        }
      },
    })

    return () => {
      conn.close()
    }
  }, [merchant, fetchActions, fetchDashboard, fetchCapabilities, fetchEligibleTrust])

  // ── Action handlers ────────────────────────────────────────────────────────

  /** Called by DecisionFeed → OptionCard after a successful approve */
  const handleApproveAction = useCallback(
    (id: string) => {
      setPendingActions((prev) => prev.filter((a) => a.id !== id))
      if (merchant) fetchDashboard(merchant.slug)
    },
    [merchant, fetchDashboard],
  )

  /** Called by DecisionFeed → OptionCard after a successful dismiss */
  const handleDismissAction = useCallback((id: string) => {
    setPendingActions((prev) => prev.filter((a) => a.id !== id))
  }, [])

  const handleReview = useCallback(async () => {
    if (!merchant || reviewState !== 'idle') return
    setReviewState('sending')
    try {
      // Unlike simulate, this call awaits the real cycle server-side and
      // returns the result directly — no anomaly to wait on. The resulting
      // card (if any) still arrives via the normal WS `agent_action` push.
      const action = await api.runStoreReview()
      setReviewState(action ? 'found' : 'clean')
    } catch {
      // A real request failure is not the same as "catalog looks healthy" —
      // show it as its own state instead of a false-positive "clean".
      setReviewState('error')
    }
    window.setTimeout(() => setReviewState('idle'), 4000)
  }, [merchant, reviewState])

  // ── Render ─────────────────────────────────────────────────────────────────

  if (authLoading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: 'var(--color-bg)' }}
      >
        <p className="text-sm font-mono" style={{ color: 'var(--color-text-muted)' }}>
          Loading…
        </p>
      </div>
    )
  }

  // Redirect is in-flight; render nothing so the page doesn't flash
  if (!merchant) return null

  const wsColor =
    wsStatus === 'connected'
      ? '#4ade80'
      : wsStatus === 'connecting'
      ? 'var(--color-warning)'
      : 'var(--color-danger)'

  return (
    <main className="min-h-screen" style={{ background: 'var(--color-bg)', color: 'var(--color-text)' }}>
      {/* ── Header ── */}
      <header
        className="sticky top-0 z-10 border-b px-6 py-4 flex flex-wrap items-center justify-between gap-y-3"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
      >
        <div className="whitespace-nowrap">
          <h1
            className="text-lg font-semibold"
            style={{ fontFamily: 'var(--font-display)', color: 'var(--color-text)' }}
          >
            {merchant.store_name}
          </h1>
          <p className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
            Merchant Terminal
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className="whitespace-nowrap text-[10px] font-mono px-2 py-0.5 rounded-full"
                style={{ background: 'rgba(110,231,183,0.12)', color: 'var(--color-accent)' }}>
            ✦ qwen-max · Remembers {memoryCount ?? 0} previous decision{memoryCount === 1 ? '' : 's'}
            {lastTokens != null ? ` · ~${lastTokens.toLocaleString()} tokens` : ''}
          </span>
          <a
            href={`/builder?slug=${merchant.slug}`}
            className="whitespace-nowrap text-xs font-medium px-3 py-1.5 rounded-md transition-opacity hover:opacity-90"
            style={{ background: 'var(--color-accent)', color: 'var(--color-bg)' }}
          >
            Customize store
          </a>
          <a
            href="/products"
            className="whitespace-nowrap text-xs font-mono px-3 py-1.5 rounded-md border transition-colors hover:opacity-80"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            Products
          </a>
          <a
            href="/terminal/decisions"
            className="whitespace-nowrap text-xs font-mono px-3 py-1.5 rounded-md border transition-colors hover:opacity-80"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            Decision trace
          </a>
          <a
            href={`/s/${merchant.slug}`}
            target="_blank"
            rel="noreferrer"
            className="whitespace-nowrap text-xs font-mono px-3 py-1.5 rounded-md border transition-colors hover:opacity-80"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            View store ↗
          </a>
          <a
            href="/logout"
            className="whitespace-nowrap text-xs font-mono px-3 py-1.5 rounded-md border transition-colors hover:opacity-80"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            Sign out
          </a>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: wsColor }} />
            <span className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
              {wsStatus}
            </span>
          </span>
        </div>
      </header>

      {/* ── Qwen fallback notification (transient, auto-dismisses) ── */}
      {qwenFallback && (
        <div className="px-6 pt-3 max-w-[1400px] mx-auto">
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm animate-in fade-in slide-in-from-top-1 duration-300"
               style={{
                 background: 'rgba(255, 209, 102, 0.1)',
                 border: '1px solid rgba(255, 209, 102, 0.25)',
                 color: 'var(--color-warning, #FFD166)',
               }}>
            <span className="text-base">⚡</span>
            <span className="flex-1 font-mono">{qwenFallback.message}</span>
            <button onClick={() => setQwenFallback(null)}
                    className="text-xs opacity-60 hover:opacity-100 transition-opacity">
              ✕
            </button>
          </div>
        </div>
      )}

      {/* ── Interceptor clamp alert (manual dismiss, no auto-timeout) ── */}
      {clampAlert && (
        <div className="px-6 pt-3 max-w-[1400px] mx-auto">
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg text-sm animate-in fade-in slide-in-from-top-1 duration-300"
               style={{
                 background: 'rgba(255, 209, 102, 0.1)',
                 border: '1px solid rgba(255, 209, 102, 0.25)',
                 color: 'var(--color-warning, #FFD166)',
               }}>
            <span className="text-base">⚠</span>
            <span className="flex-1 font-mono">Clamped on approval: {clampAlert}</span>
            <button onClick={() => setClampAlert(null)}
                    className="text-xs opacity-60 hover:opacity-100 transition-opacity">
              ✕
            </button>
          </div>
        </div>
      )}

      {/* ── Auto-applied FYI (manual dismiss, no auto-timeout) — the one path
          that skips the approval card entirely, so it's the one that most
          needs an explicit "here's what just happened and why." ── */}
      {autoExecutedAlert && (
        <div className="px-6 pt-3 max-w-[1400px] mx-auto">
          <div className="flex items-start gap-3 px-4 py-3 rounded-lg text-sm animate-in fade-in slide-in-from-top-1 duration-300"
               style={{
                 background: 'var(--color-accent-dim, rgba(110,231,183,0.1))',
                 border: '1px solid var(--color-accent)',
                 color: 'var(--color-accent)',
               }}>
            <span className="text-base">✦</span>
            <div className="flex-1 min-w-0">
              <p className="font-mono font-semibold">Auto-applied: {autoExecutedAlert.title}</p>
              {autoExecutedAlert.reasoning && (
                <p className="text-xs font-mono mt-1" style={{ color: 'var(--color-text-muted)' }}>
                  {autoExecutedAlert.reasoning}
                </p>
              )}
            </div>
            <button onClick={() => setAutoExecutedAlert(null)}
                    className="text-xs opacity-60 hover:opacity-100 transition-opacity shrink-0">
              ✕
            </button>
          </div>
        </div>
      )}

      {/* ── Two zones: what needs a decision now (left, wide) vs. store state
          & config (right, narrower sidebar) — everything in the left column
          shares one width so a pending-product card, a capability proposal,
          and a decision card read as the same kind of thing (they are: all
          three are "Qwen wants you to decide something"), instead of three
          different layout conventions stacked with no visual relationship. ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 px-6 pt-6 pb-10 max-w-[1400px] mx-auto items-start">
        {/* Left: the decision feed — agent actions lead (these carry a 5-minute
            TTL and can expire unacted-on, so they're the most time-sensitive
            thing on the page), then capability proposals, then pending
            products (no expiry — they just wait, so they're lowest urgency). */}
        <div className="flex flex-col gap-6 min-w-0">
          <DecisionFeed
            actions={pendingActions}
            slug={merchant.slug}
            onApproveAction={handleApproveAction}
            onDismissAction={handleDismissAction}
            onClamped={handleClamped}
          />

          <CapabilityProposals capabilities={capabilities} />

          <EarnedTrustPanel
            eligible={eligibleTrust}
            onToggled={(updated) => {
              setEligibleTrust((prev) =>
                prev.map((e) =>
                  e.product_id === updated.product_id && e.action_type === updated.action_type ? updated : e
                )
              )
            }}
          />

          {pendingProducts.length > 0 && (
            <div className="flex flex-col gap-3">
              <p className="font-mono text-xs uppercase tracking-widest" style={{ color: 'var(--color-accent)' }}>
                Product Vision · {pendingProducts.length} awaiting approval
              </p>
              <AnimatePresence>
                {pendingProducts.map((p) => (
                  <PendingProductCard
                    key={p.id}
                    product={p}
                    onApproved={(approved) => setPendingProducts((prev) => prev.filter((x) => x.id !== approved.id))}
                    onDiscarded={(id) => setPendingProducts((prev) => prev.filter((x) => x.id !== id))}
                  />
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* Right: store state, stats, and the limits Qwen operates within —
            reference/glanceable, not time-sensitive, so it sits apart from
            the decision feed rather than competing with it for attention. */}
        <div className="flex flex-col gap-6 min-w-0">
          <StoreSnapshot
            merchant={merchant}
            slug={merchant.slug}
            onReview={handleReview}
            reviewState={reviewState}
          />
          <AttributionDashboard data={dashboard} loading={dashboardLoading} />
          <SearchDemandInsights slug={merchant.slug} />
          <ConstraintsSettings />
        </div>
      </div>
    </main>
  )
}
