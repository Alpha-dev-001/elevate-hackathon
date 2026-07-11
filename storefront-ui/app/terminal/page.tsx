'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { api, ApiError, type DashboardData, type Capability } from '@/lib/api'
import { connectTerminal } from '@/lib/ws'
import type { AgentAction, Merchant } from '@/types/schemas'
import { StoreSnapshot } from '@/components/terminal/StoreSnapshot'
import { DecisionFeed } from '@/components/terminal/DecisionFeed'
import { AttributionDashboard } from '@/components/terminal/AttributionDashboard'
import { CapabilityProposals } from '@/components/terminal/CapabilityProposals'

export default function TerminalPage() {
  const router = useRouter()

  const [merchant, setMerchant] = useState<Merchant | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [pendingActions, setPendingActions] = useState<AgentAction[]>([])
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [dashboardLoading, setDashboardLoading] = useState(false)
  const [simulateState, setSimulateState] = useState<'idle' | 'sending' | 'done'>('idle')
  const [reviewState, setReviewState] = useState<'idle' | 'sending' | 'found' | 'clean' | 'error'>('idle')
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [memoryCount, setMemoryCount] = useState<number | null>(null)
  const [lastTokens, setLastTokens] = useState<number | null>(null)
  const [capabilities, setCapabilities] = useState<Capability[]>([])
  const [qwenFallback, setQwenFallback] = useState<{ message: string; type: string } | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

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

  // ── Subscriptions ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (!merchant) return
    const { slug, id } = merchant

    // Initial fetch
    fetchActions(slug)
    fetchDashboard(slug)
    fetchCapabilities(slug)

    // 5s poll for new actions + capability gaps (capability changes originate in
    // the builder's point-and-edit flow, so the terminal learns of them by poll).
    pollRef.current = setInterval(() => {
      fetchActions(slug)
      fetchCapabilities(slug)
    }, 5000)

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
        }
      },
    })

    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      conn.close()
    }
  }, [merchant, fetchActions, fetchDashboard, fetchCapabilities])

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

  const handleSimulate = useCallback(
    async (scenario: 'cart_abandon_surge' | 'velocity_spike') => {
      if (!merchant || simulateState !== 'idle') return
      setSimulateState('sending')
      try {
        await api.simulateActivity(merchant.slug, scenario)
      } catch {
        // the scenario may still be queued server-side — keep waiting for the decision
      }
      // Stay in 'sending' until a new decision card arrives (effect below). Safety
      // timeout so the button never gets stuck if no anomaly ends up firing.
      window.setTimeout(() => {
        setSimulateState((s) => (s === 'sending' ? 'idle' : s))
      }, 30000)
    },
    [merchant, simulateState],
  )

  // Flip 'sending' → 'done' the moment Qwen's decision card actually lands, so
  // the merchant sees the loop resolve instead of a button that seems to do nothing.
  const prevActionCount = useRef(0)
  useEffect(() => {
    if (simulateState === 'sending' && pendingActions.length > prevActionCount.current) {
      setSimulateState('done')
      window.setTimeout(() => setSimulateState('idle'), 4000)
    }
    prevActionCount.current = pendingActions.length
  }, [pendingActions.length, simulateState])

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
        className="sticky top-0 z-10 border-b px-6 py-4 flex items-center justify-between"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
      >
        <div>
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

        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full"
                style={{ background: 'rgba(110,231,183,0.12)', color: 'var(--color-accent)' }}>
            ✦ qwen-max · Remembers {memoryCount ?? 0} previous decision{memoryCount === 1 ? '' : 's'}
            {lastTokens != null ? ` · ~${lastTokens.toLocaleString()} tokens` : ''}
          </span>
          <a
            href={`/builder?slug=${merchant.slug}`}
            className="text-xs font-medium px-3 py-1.5 rounded-md transition-opacity hover:opacity-90"
            style={{ background: 'var(--color-accent)', color: 'var(--color-bg)' }}
          >
            Customize store
          </a>
          <a
            href="/products"
            className="text-xs font-mono px-3 py-1.5 rounded-md border transition-colors hover:opacity-80"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            Products
          </a>
          <a
            href={`/s/${merchant.slug}`}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-mono px-3 py-1.5 rounded-md border transition-colors hover:opacity-80"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            View store ↗
          </a>
          <a
            href="/logout"
            className="text-xs font-mono px-3 py-1.5 rounded-md border transition-colors hover:opacity-80"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
          >
            Sign out
          </a>
          <span className="w-2 h-2 rounded-full" style={{ background: wsColor }} />
          <span className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
            {wsStatus}
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

      {/* ── Qwen capability proposals (surfaces only when there are any) ── */}
      <div className="px-6 pt-6 max-w-[1400px] mx-auto">
        <CapabilityProposals capabilities={capabilities} />
      </div>

      {/* ── 3-column layout ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 px-6 pb-6 max-w-[1400px] mx-auto">
        {/* Left: Store snapshot + simulate */}
        <div className="lg:col-span-1">
          <StoreSnapshot
            merchant={merchant}
            slug={merchant.slug}
            onSimulate={handleSimulate}
            simulateState={simulateState}
            onReview={handleReview}
            reviewState={reviewState}
          />
        </div>

        {/* Center: Decision feed */}
        <div className="lg:col-span-1">
          <DecisionFeed
            actions={pendingActions}
            slug={merchant.slug}
            onApproveAction={handleApproveAction}
            onDismissAction={handleDismissAction}
          />
        </div>

        {/* Right: Attribution dashboard */}
        <div className="lg:col-span-1">
          <AttributionDashboard data={dashboard} loading={dashboardLoading} />
        </div>
      </div>
    </main>
  )
}
