/**
 * Customer behavior tracking — feeds the autopilot telemetry loop.
 *
 * Connects to the storefront WebSocket's sendEvent to emit view, add_to_cart,
 * and abandon events. These events flow through the backend's behavior_tracker
 * → anomaly detection → decision cycle pipeline.
 *
 * Usage:
 *   1. Call initBehaviorTracking(sendEvent, merchantId, sessionId) when WS connects
 *   2. Call trackProductView(productId) when a product enters the viewport
 *   3. Call trackAddToCart(productId) when a customer adds to cart
 *   4. Abandon detection is automatic (page visibility change + inactivity)
 */

type SendEventFn = (event: Record<string, unknown>) => void

let _sendEvent: SendEventFn | null = null
let _merchantId: string | null = null
let _sessionId: string | null = null

// Dedup: don't fire the same product view twice within 30 seconds
const _recentViews = new Map<string, number>()
const VIEW_DEDUP_MS = 30_000

// Session ID: persists for the browser tab lifetime
function getOrCreateSessionId(): string {
  if (_sessionId) return _sessionId
  const key = 'elevate_session_id'
  let sid = sessionStorage.getItem(key)
  if (!sid) {
    sid = `sess_${Math.random().toString(36).slice(2, 10)}_${Date.now()}`
    sessionStorage.setItem(key, sid)
  }
  _sessionId = sid
  return sid
}

/**
 * Initialize behavior tracking. Call once when the storefront WS connects.
 */
export function initBehaviorTracking(
  sendEvent: SendEventFn,
  merchantId: string,
) {
  _sendEvent = sendEvent
  _merchantId = merchantId
  _sessionId = getOrCreateSessionId()

  // Auto-detect page leave / tab switch → potential abandon
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange)
  }
}

/**
 * Clean up listeners. Call when the storefront WS disconnects.
 */
export function cleanupBehaviorTracking() {
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  }
  _sendEvent = null
  _merchantId = null
}

function emit(eventType: string, productId: string = '') {
  if (!_sendEvent || !_merchantId || !_sessionId) return
  _sendEvent({
    event_type: eventType,
    product_id: productId,
    session_id: _sessionId,
    timestamp: Date.now() / 1000,
  })
}

/**
 * Track a product view. Deduplicated — same product won't fire twice within 30s.
 * Call this when a product card enters the viewport or a product page loads.
 */
export function trackProductView(productId: string) {
  if (!productId) return
  const now = Date.now()
  const last = _recentViews.get(productId) || 0
  if (now - last < VIEW_DEDUP_MS) return
  _recentViews.set(productId, now)
  emit('view', productId)
}

/**
 * Track an add-to-cart event. Not deduplicated — each add matters.
 */
export function trackAddToCart(productId: string) {
  if (!productId) return
  emit('add_to_cart', productId)
}

// ── Abandon detection ─────────────────────────────────────────────────────────

let _hasInteracted = false
let _abandonFired = false

/**
 * Mark that the customer has interacted (viewed products, scrolled, etc.).
 * Abandon only fires if the customer actually engaged before leaving.
 */
export function markInteracted() {
  _hasInteracted = true
}

function handleVisibilityChange() {
  if (document.visibilityState === 'hidden' && _hasInteracted && !_abandonFired) {
    // Customer left the tab / closed the window after browsing
    _abandonFired = true
    emit('abandon')
  }
  // Reset on return so a second leave can fire again
  if (document.visibilityState === 'visible') {
    _abandonFired = false
  }
}
