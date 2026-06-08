import type { QwenDecisionRequest, QwenDecision, ProposedAction } from '@/types'

const QWEN_BASE = process.env.QWEN_API_BASE || 'https://dashscope.aliyuncs.com/compatible-mode/v1'
const QWEN_MODEL = process.env.QWEN_MODEL || 'qwen-max'

// ─── System prompt — defines Qwen's role as the runtime engine ────────────────

const SYSTEM_PROMPT = `You are Elevate's autonomous merchant intelligence engine.

Your role is NOT to chat. You receive a structured business context and return 
structured decisions. You are the runtime brain — the code is the body.

RULES:
- Never suggest actions that violate the merchant's BusinessProfile constraints
- All price changes must keep margin above minProfitMarginPercent
- All discounts must stay below maxDiscountPercent
- Return ONLY valid JSON matching the QwenDecision schema — no prose, no markdown
- Propose maximum 3 actions per decision cycle — clarity over quantity
- Order actions by estimated impact descending
- Flag any action with risk > 'safe' explicitly in riskLevel

Your output is machine-consumed. Precision over explanation.`

// ─── Decision request ─────────────────────────────────────────────────────────

export async function requestDecision(
  request: QwenDecisionRequest
): Promise<QwenDecision> {
  const response = await fetch(`${QWEN_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${process.env.QWEN_API_KEY}`,
    },
    body: JSON.stringify({
      model: QWEN_MODEL,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: buildDecisionPrompt(request) },
      ],
      response_format: { type: 'json_object' },
      temperature: 0.3,  // low temp — we want consistent, reliable decisions
      max_tokens: 2048,
    }),
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`[Qwen] Decision request failed: ${error}`)
  }

  const data = await response.json()
  const raw = data.choices?.[0]?.message?.content

  if (!raw) throw new Error('[Qwen] Empty response from model')

  try {
    return JSON.parse(raw) as QwenDecision
  } catch {
    throw new Error(`[Qwen] Failed to parse decision JSON: ${raw}`)
  }
}

// ─── Prompt builder ───────────────────────────────────────────────────────────

function buildDecisionPrompt(request: QwenDecisionRequest): string {
  const { snapshot, profile, currentState } = request

  return JSON.stringify({
    instruction: 'Analyze the telemetry snapshot and propose business actions. Return a QwenDecision JSON object.',
    schema: {
      reasoning: 'string — your analysis in 1-2 sentences',
      proposedActions: 'ProposedAction[] — max 3 actions ordered by impact',
      urgency: 'routine | moderate | urgent',
      estimatedImpact: 'string — one line revenue/engagement prediction',
    },
    context: {
      snapshot,
      businessConstraints: profile.constraints,
      products: profile.products,
      currentPromos: Object.values(currentState.activePromos),
      currentLayout: currentState.layoutConfig,
    },
  })
}

// ─── Memory context builder (Track 1 crossover) ───────────────────────────────
// Accumulates merchant decision history to improve future recommendations

export async function buildMemoryContext(
  merchantId: string,
  recentDeltas: unknown[]
): Promise<string> {
  if (recentDeltas.length === 0) return ''

  const response = await fetch(`${QWEN_BASE}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${process.env.QWEN_API_KEY}`,
    },
    body: JSON.stringify({
      model: QWEN_MODEL,
      messages: [
        {
          role: 'system',
          content: 'Summarize merchant decision patterns from delta history into a brief memory context (max 100 words) that will improve future recommendations. Return plain text only.',
        },
        {
          role: 'user',
          content: JSON.stringify({ merchantId, recentDeltas }),
        },
      ],
      max_tokens: 200,
      temperature: 0.2,
    }),
  })

  const data = await response.json()
  return data.choices?.[0]?.message?.content || ''
}
