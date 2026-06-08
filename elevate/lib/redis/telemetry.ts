import type { CustomerEvent, TelemetrySnapshot, Anomaly } from '@/types'
import { getRedisClient, KEYS, TTL } from '@/lib/redis/client'

// ─── Telemetry Snapshot Layer ─────────────────────────────────────────────────

export async function recordEvent(
  merchantId: string,
  event: CustomerEvent
): Promise<void> {
  const redis = getRedisClient()

  // Track product velocity (views per product in sliding window)
  if (event.eventType === 'view') {
    await redis.zincrby(KEYS.productVelocity(merchantId), 1, event.productId)
    await redis.expire(KEYS.productVelocity(merchantId), 300) // 5 min window
  }

  // Store session event
  await redis.lpush(
    KEYS.sessionEvents(event.sessionId),
    JSON.stringify(event)
  )
  await redis.expire(KEYS.sessionEvents(event.sessionId), TTL.session)

  // Increment active session count
  await redis.sadd(`elevate:${merchantId}:active_sessions`, event.sessionId)
  await redis.expire(`elevate:${merchantId}:active_sessions`, 300)
}

export async function captureSnapshot(merchantId: string): Promise<TelemetrySnapshot> {
  const redis = getRedisClient()

  // Get active sessions
  const activeSessions = await redis.scard(`elevate:${merchantId}:active_sessions`)

  // Get product velocity scores
  const velocityData = await redis.zrevrange(
    KEYS.productVelocity(merchantId),
    0,
    -1,
    'WITHSCORES'
  )

  const productVelocity: Record<string, number> = {}
  for (let i = 0; i < velocityData.length; i += 2) {
    productVelocity[velocityData[i]] = parseFloat(velocityData[i + 1])
  }

  const hotProducts = velocityData
    .filter((_, i) => i % 2 === 0)
    .slice(0, 5)

  // Detect anomalies
  const anomalies = detectAnomalies(productVelocity, activeSessions)

  const snapshot: TelemetrySnapshot = {
    capturedAt: Date.now(),
    activeSessionCount: activeSessions,
    productVelocity,
    transactionRate: 0, // populated by purchase events
    abandonRate: 0,     // populated by session analysis
    hotProducts,
    anomalies,
  }

  // Cache snapshot
  await redis.set(
    KEYS.snapshot(merchantId),
    JSON.stringify(snapshot),
    'EX',
    TTL.snapshot
  )

  return snapshot
}

// ─── Anomaly detection ────────────────────────────────────────────────────────

function detectAnomalies(
  productVelocity: Record<string, number>,
  activeSessions: number
): Anomaly[] {
  const anomalies: Anomaly[] = []
  const velocities = Object.values(productVelocity)

  if (velocities.length === 0) return anomalies

  const avgVelocity = velocities.reduce((a, b) => a + b, 0) / velocities.length

  for (const [productId, velocity] of Object.entries(productVelocity)) {
    // Velocity spike: 3x above average
    if (velocity > avgVelocity * 3) {
      anomalies.push({
        type: 'velocity_spike',
        productId,
        severity: velocity > avgVelocity * 5 ? 'high' : 'medium',
        detectedAt: Date.now(),
        context: { velocity, avgVelocity, ratio: velocity / avgVelocity },
      })
    }

    // Dead product: zero velocity while others are active
    if (velocity === 0 && activeSessions > 5) {
      anomalies.push({
        type: 'dead_product',
        productId,
        severity: 'low',
        detectedAt: Date.now(),
        context: { activeSessions },
      })
    }
  }

  return anomalies
}
