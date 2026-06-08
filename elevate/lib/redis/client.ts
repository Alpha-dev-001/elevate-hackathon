import Redis from 'ioredis'

// ─── Singleton Redis client (Alibaba Cloud Tair compatible) ───────────────────

let client: Redis | null = null

export function getRedisClient(): Redis {
  if (client) return client

  client = new Redis({
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379'),
    password: process.env.REDIS_PASSWORD,
    retryStrategy: (times) => Math.min(times * 100, 3000),
    maxRetriesPerRequest: 3,
    lazyConnect: true,
  })

  client.on('error', (err) => {
    console.error('[Redis] Connection error:', err.message)
  })

  client.on('connect', () => {
    console.log('[Redis] Connected to Alibaba Cloud Tair')
  })

  return client
}

// ─── Key schema ───────────────────────────────────────────────────────────────

export const KEYS = {
  systemState: (merchantId: string) => `elevate:${merchantId}:state`,
  telemetry: (merchantId: string) => `elevate:${merchantId}:telemetry`,
  snapshot: (merchantId: string) => `elevate:${merchantId}:snapshot:latest`,
  deltaLog: (merchantId: string) => `elevate:${merchantId}:deltas`,
  sessionEvents: (sessionId: string) => `elevate:session:${sessionId}`,
  productVelocity: (merchantId: string) => `elevate:${merchantId}:velocity`,
  pendingActions: (merchantId: string) => `elevate:${merchantId}:pending_actions`,
} as const

// ─── TTLs (seconds) ───────────────────────────────────────────────────────────

export const TTL = {
  snapshot: 300,        // 5 min — telemetry snapshots
  session: 1800,        // 30 min — customer sessions
  pendingActions: 3600, // 1 hour — merchant action queue
  deltaLog: 86400 * 7,  // 7 days — audit trail
} as const
