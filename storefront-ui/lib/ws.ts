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

export interface TerminalHandlers {
  onBrandReady?: (payload: BrandReadyPayload) => void
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
