/**
 * Terminal WebSocket client.
 *
 * The merchant's terminal listens here for server pushes — during onboarding
 * that's `brand_ready` (the brand package, or an error). All live data flows
 * over this socket; there is no polling. Reconnects with backoff unless the
 * caller closed it deliberately.
 */
import { WS_BASE } from './api'
import { BrandReadyPayloadSchema } from '@/types/schemas'
import type { BrandReadyPayload } from '@/types/schemas'

export interface QwenFallbackPayload {
  type: string
  store_name: string
  reason: string
  message: string
}

export interface TerminalHandlers {
  onBrandReady?: (payload: BrandReadyPayload) => void
  /** Fired when a Qwen call fails and the backend falls back to a deterministic
   *  path (e.g. layout DSL). The merchant should see this — it's transparency
   *  about the autopilot's degradation, not a hidden error. */
  onQwenFallback?: (payload: QwenFallbackPayload) => void
  onOpen?: () => void
  onClose?: () => void
  /** Any event, post-parse — useful for events we don't special-case yet. */
  onEvent?: (event: string, payload: Record<string, unknown>) => void
}

export interface TerminalConnection {
  close: () => void
}

export function connectTerminal(
  merchantId: string,
  handlers: TerminalHandlers,
): TerminalConnection {
  let socket: WebSocket | null = null
  let closedByCaller = false
  let attempt = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  const url = `${WS_BASE}/terminal/${merchantId}`

  const open = () => {
    socket = new WebSocket(url)

    socket.onopen = () => {
      attempt = 0
      handlers.onOpen?.()
    }

    socket.onmessage = (ev) => {
      let msg: { event?: string; payload?: Record<string, unknown> }
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return // ignore non-JSON frames
      }
      if (!msg.event) return
      handlers.onEvent?.(msg.event, msg.payload ?? {})

      if (msg.event === 'brand_ready') {
        const parsed = BrandReadyPayloadSchema.safeParse(msg.payload)
        if (parsed.success) {
          handlers.onBrandReady?.(parsed.data)
        } else {
          // Malformed payload — surface as an error rather than hanging.
          handlers.onBrandReady?.({ error: 'Received a malformed brand payload' })
        }
      }

      if (msg.event === 'qwen_fallback' && msg.payload) {
        handlers.onQwenFallback?.(msg.payload as unknown as QwenFallbackPayload)
      }
    }

    socket.onclose = () => {
      handlers.onClose?.()
      if (closedByCaller) return
      // Exponential backoff, capped — survive a backend blip mid-onboarding.
      attempt += 1
      const delay = Math.min(1000 * 2 ** (attempt - 1), 8000)
      reconnectTimer = setTimeout(open, delay)
    }

    socket.onerror = () => {
      socket?.close()
    }
  }

  open()

  return {
    close: () => {
      closedByCaller = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      socket?.close()
    },
  }
}

// ── Storefront (customer) socket ──────────────────────────────────────────────

export interface StorefrontHandlers {
  /** Fired on any state_updated push (approve, rollback, promo) — refetch/morph. */
  onStateUpdated?: (payload: Record<string, unknown>) => void
  onOpen?: () => void
  onClose?: () => void
}

export interface StorefrontConnection {
  close: () => void
  /** Emit a customer behavior event into the telemetry loop (view, abandon, …). */
  sendEvent: (event: Record<string, unknown>) => void
}

/**
 * The live customer store socket. This is the other half of the nervous system:
 * the merchant approves in the terminal, the backend broadcasts state_updated to
 * every connected storefront, and the shopper's store morphs — no reload, no
 * polling. Reconnects with backoff so a blip doesn't silently kill live updates.
 */
export function connectStorefront(
  merchantId: string,
  handlers: StorefrontHandlers,
): StorefrontConnection {
  let socket: WebSocket | null = null
  let closedByCaller = false
  let attempt = 0
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  const url = `${WS_BASE}/storefront/${merchantId}`

  const open = () => {
    socket = new WebSocket(url)

    socket.onopen = () => {
      attempt = 0
      handlers.onOpen?.()
    }

    socket.onmessage = (ev) => {
      let msg: { event?: string; payload?: Record<string, unknown> }
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      if (msg.event === 'state_updated') {
        handlers.onStateUpdated?.(msg.payload ?? {})
      }
    }

    socket.onclose = () => {
      handlers.onClose?.()
      if (closedByCaller) return
      attempt += 1
      const delay = Math.min(1000 * 2 ** (attempt - 1), 8000)
      reconnectTimer = setTimeout(open, delay)
    }

    socket.onerror = () => {
      socket?.close()
    }
  }

  open()

  return {
    close: () => {
      closedByCaller = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      socket?.close()
    },
    sendEvent: (event) => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ event: 'customer_event', payload: { event } }))
      }
    },
  }
}
