'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { api, ApiError, type DashboardData } from '@/lib/api'
import { connectTerminal } from '@/lib/ws'
import type { AgentAction, Merchant } from '@/types/schemas'
import { StoreSnapshot } from '@/components/terminal/StoreSnapshot'
import { DecisionFeed } from '@/components/terminal/DecisionFeed'
import { AttributionDashboard } from '@/components/terminal/AttributionDashboard'

export default function TerminalPage() {
  const router = useRouter()

  const [merchant, setMerchant] = useState<Merchant | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [pendingActions, setPendingActions] = useState<AgentAction[]>([])
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [dashboardLoading, setDashboardLoading] = useState(false)
  const [simulateState, setSimulateState] = useState<'idle' | 'sending' | 'done'>('idle')
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [memoryCount, setMemoryCount] = useState<number | null>(null)
  const [lastTokens, setLastTokens] = useState<number | null>(null)

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
    } catch {
      // keep stale data rather than crashing
    } finally {
      setDashboardLoading(false)
    }
  }, [])

  // ── Subscriptions ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (!merchant) return
    const { slug, id } = merchant

    // Initial fetch
    fetchActions(slug)
    fetchDashboard(slug)

    // 5s poll for new actions (fallback — WS is primary)
    pollRef.current = setInterval(() => fetchActions(slug), 5000)

    // WS subscription
    const conn = connectTerminal(id, {
      onOpen: () => setWsStatus('connected'),
      onClose: () => setWsStatus('disconnected'),
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
        if (event === 'state_updated') {
          fetchDashboard(slug)
        }
      },
    })

    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      conn.close()
    }
  }, [merchant, fetchActions, fetchDashboard])

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

  const handleSimulate = useCallback(async () => {
    if (!merchant || simulateState !== 'idle') return
    setSimulateState('sending')
    try {
      await api.simulateActivity(merchant.slug)
    } catch {
      // show done regardless — the scenario may have been queued server-side
    }
    setSimulateState('done')
    setTimeout(() => setSimulateState('idle'), 3000)
  }, [merchant, simulateState])

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
          <span className="w-2 h-2 rounded-full" style={{ background: wsColor }} />
          <span className="text-xs font-mono" style={{ color: 'var(--color-text-muted)' }}>
            {wsStatus}
          </span>
        </div>
      </header>

      {/* ── 3-column layout ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 p-6 max-w-[1400px] mx-auto">
        {/* Left: Store snapshot + simulate */}
        <div className="lg:col-span-1">
          <StoreSnapshot
            merchant={merchant}
            slug={merchant.slug}
            onSimulate={handleSimulate}
            simulateState={simulateState}
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
