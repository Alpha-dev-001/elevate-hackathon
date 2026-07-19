"""
Qwen decision engine — reads store state + behavior anomaly, fires one action.
Called when behavior_tracker detects an anomaly threshold crossing.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from uuid import uuid4
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.services.qwen_roles import QwenRole

from app.models.schemas import AgentAction, AgentActionStatus, AgentActionType, WSEventType
from app.models.db_models import AgentActionDB, MerchantDB, BrandProfileDB, ProductDB
from app.services.brand import _qwen_chat, _extract_json, BrandGenerationError
from app.services.tools import DECISION_TOOLS, TOOL_TO_ACTION_TYPE, narrative_from_tool, parse_tool_args
from app.services.action_guard import validate_tool_args, ActionValidationError
from app.core.ws_manager import manager
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Action types whose premise is a structural/catalog fact, not a live signal —
# duplicate SKUs or an underperforming product don't resolve themselves on a
# clock the way a velocity spike or a dwelling cart does. These use the longer
# pending_action_ttl_seconds_durable instead of the short reactive-trigger TTL,
# so a card doesn't vanish on a merchant (or a judge) who takes >5 minutes to
# read the reasoning before approving.
DURABLE_ACTION_TYPES = frozenset({
    AgentActionType.DUPLICATE_MERGE,
    AgentActionType.LAYOUT_MORPH,
    AgentActionType.COPY_REWRITE,
    AgentActionType.FEATURE_PRODUCT,
    AgentActionType.PRICE_REBALANCE,
})


def _pending_ttl_for(action_type: str) -> int:
    settings = get_settings()
    try:
        is_durable = AgentActionType(action_type) in DURABLE_ACTION_TYPES
    except ValueError:
        is_durable = False
    return settings.pending_action_ttl_seconds_durable if is_durable else settings.pending_action_ttl_seconds

DECISION_PROMPT = """{role_intro}
Brand mood: {mood} | Voice: {brand_voice}
Brand rules (never violate): {brand_rules_summary}

Current products: {products_summary}
Behavior anomaly: {anomaly_description}
{memory_block}
Use the available tools to propose ONE action for the merchant to review.
Every tool has a required "reasoning" argument — fill it with your step-by-step
reasoning: what you observed, why this action makes sense, and what outcome you
expect (be specific with numbers). This is what the merchant sees explaining
your call, so it must stand on its own.

A recovery_offer is an ORDER-LEVEL percentage discount on the shopper's existing
cart to win back an abandoned checkout — this store has no shipping concept, so
never propose free shipping.

This merchant's actual discount ceiling is {max_discount_percent:g}% — any
flash_sale, scarcity_price, or recovery_offer discount you propose is allowed
to use the real headroom up to that ceiling when the anomaly justifies it, not
just a safe-sounding round number. Reason about how much of that headroom this
specific anomaly actually earns; a discount below the ceiling is a choice you
should be able to defend with the anomaly's magnitude, not a default.

The merchant approves before execution. Make it compelling."""


def _extract_count(anomaly_desc: str) -> int:
    """The anomaly magnitude captured at trigger time (e.g. '5 abandons', '24
    views') — the honest basis for a revenue estimate. 0 if none found."""
    import re
    m = re.search(r"\d+", anomaly_desc or "")
    return int(m.group()) if m else 0


def extract_reasoning(tool_args: dict, message: dict) -> str:
    """Every DECISION_TOOLS entry (except propose_price_rebalance, which
    already carries reasoning_signals) requires a "reasoning" argument in
    its own schema — a structured field Qwen reliably fills, unlike the
    freeform message.content alongside a tool call, which tool-calling
    Qwen omits almost every time regardless of what the prompt asks for.
    message.content is kept only as a last-resort fallback for a tool call
    made under an older/external schema that carries neither field."""
    return (
        tool_args.get("reasoning")
        or tool_args.get("reasoning_signals")
        or message.get("content")
        or ""
    )[:1000]


def grounded_gmv(action_type: str, anomaly_count: int, avg_price: float) -> float:
    """A revenue-impact estimate tied to REAL signals instead of a Qwen guess:
    the anomaly magnitude × the catalog's average price × a tunable per-type rate.
    Returns 0.0 when we can't ground it (caller then falls back to Qwen's number)."""
    if action_type in ("duplicate_merge", "price_rebalance"):
        # duplicate_merge: catalog-hygiene action, no grounded revenue basis.
        # price_rebalance: a repricing's impact isn't "anomaly count × avg
        # price × rate" — there's no anomaly count in the same sense here.
        return 0.0
    if avg_price <= 0 or anomaly_count <= 0:
        return 0.0
    s = get_settings()
    rate = s.recovery_gmv_rate if action_type == "recovery_offer" else s.flash_gmv_rate
    return round(anomaly_count * avg_price * rate, 2)


def compose_decision_prompt(
    *,
    store_name: str,
    mood: str,
    brand_voice: str,
    brand_rules_summary: str,
    products_summary: str,
    anomaly_description: str,
    memory_context: str = "",
    tool_calling: bool = True,
    max_discount_percent: float = 40.0,
    role: "QwenRole | None" = None,
) -> str:
    """Build the decision prompt, injecting prior-outcome memory when present.

    Extracted (and pure) so the memory-injection behavior is unit-testable
    without a DB, Redis, or a live Qwen call.

    tool_calling=False (benchmark bare-arm only) swaps the tool-instruction
    paragraph for a plain JSON-reply instruction, so a model given no tools
    isn't told to use tools it doesn't have — keeps the two benchmark arms
    different in exactly one dimension (tools/interceptor), not two.

    max_discount_percent defaults to BusinessConstraints' own schema default
    (40.0) so any caller that hasn't been updated to pass the merchant's real
    constraints yet still gets a truthful number instead of a made-up one.

    role=None (every caller not yet updated for the Qwen swarm) keeps
    today's generic "autonomous commerce brain" framing byte-identical.
    role=<a QwenRole> swaps in that role's mission_line as the prompt's
    opening line only — the rest of the template (including the discount-
    ceiling paragraph, even for a role with no discount-bearing tools) is
    deliberately left unchanged in this first pass; a fully role-specific
    template per role is a reasonable future refinement, not done here to
    keep this change reviewable as one prompt-intro swap, not four new
    prompt templates.
    """
    role_intro = (
        role.mission_line.format(store_name=store_name)
        if role is not None
        else f'You are the autonomous commerce brain for "{store_name}".'
    )
    memory_block = f"\nPrior outcomes for this store (learn from them):\n{memory_context}\n" if memory_context else ""
    prompt = DECISION_PROMPT.format(
        role_intro=role_intro,
        store_name=store_name,
        mood=mood,
        brand_voice=brand_voice,
        brand_rules_summary=brand_rules_summary,
        products_summary=products_summary,
        anomaly_description=anomaly_description,
        memory_block=memory_block,
        max_discount_percent=max_discount_percent,
    )
    if not tool_calling:
        prompt = prompt.replace(
            "Use the available tools to propose ONE action for the merchant to review.",
            'Respond with a JSON object only, no other text: '
            '{"product_id": "...", "discount_percent": <number>}.',
        ).replace(
            "The merchant approves before execution. Make it compelling.",
            "",
        )
    return prompt


async def _dismiss_pending_action(
    action: AgentActionDB, merchant_id: str, db: "AsyncSession", redis: "Redis", reason: str
) -> None:
    """Mark a pending action dismissed and fire its side effects: a ledger
    receipt, dwell suppression for a cart_dwell_nudge, and an ACTION_EXPIRED
    push so the terminal removes the card immediately. Does NOT commit — the
    caller owns the transaction boundary. The stale path commits right away;
    the priority-supersede path commits together with the replacement action,
    so the old card is never retired unless the new one is really created.
    append_receipt only flushes, never commits, so it's safe either way.

    The dismissed action's `session_id` is read into a LOCAL (dwell_session_id)
    rather than reassigning run_decision_cycle's own `session_id` parameter —
    the old code reassigned the parameter, which could leak a stale
    cart_dwell_nudge's session_id into an unrelated new action's tool_args via
    the `if session_id:` line further down. Isolating it in the helper removes
    that footgun entirely."""
    action.status = "dismissed"
    from app.services import receipts
    await receipts.append_receipt(db, merchant_id, "dismissed", action_row=action)
    if action.action_type == "cart_dwell_nudge":
        dwell_session_id = (action.payload or {}).get("session_id")
        if dwell_session_id:
            try:
                from app.services.cart_dwell import suppress_dwell_session
                await suppress_dwell_session(merchant_id, dwell_session_id, redis)
            except Exception as e:  # noqa: BLE001 — suppression must never block the cycle
                logger.warning("[decision] dwell suppression failed for %s: %s", action.id, e)
    from app.models.schemas import WSMessage
    await manager.push_to_terminal(
        merchant_id,
        WSMessage(
            event=WSEventType.ACTION_EXPIRED,
            payload={"action_id": action.id, "reason": reason},
            merchant_id=merchant_id,
            timestamp=int(time.time() * 1000),
        ),
    )


async def run_decision_cycle(
    merchant_id: str,
    anomaly_desc: str,
    db: "AsyncSession",
    redis: "Redis",
    *,
    tools: list[dict] | None = None,
    target_product_id: str | None = None,
    prompt_override: str | None = None,
    session_id: str | None = None,
    role: "QwenRole | None" = None,
    _escalation_depth: int = 0,
    _escalation_prefix: str = "",
) -> AgentAction | None:
    """Run a full Qwen decision cycle and persist + broadcast the result.

    Returns the created AgentAction or None if:
    - there is already a pending action (one at a time, unless it's stale)
    - Qwen returns garbage we can't trust

    tools/target_product_id/prompt_override are set by run_pricing_cycle
    (pricing_cycle.py) for a PRICE_REBALANCE proposal scoped to one specific
    product with its own prompt shape — every other caller leaves all three
    at their defaults and gets today's behavior unchanged. session_id is set
    by cart_dwell.py's run_dwell_check for a CART_DWELL_NUDGE proposal — it
    is written into the persisted payload AFTER Qwen's tool call and the
    interceptor clamp run, so it is never something Qwen could hallucinate
    or overwrite; agent.py's _register_recovery reads it back at approval
    time to scope the discount to that one session.

    role (the Qwen swarm — see qwen_roles.py) does two independent things:
    (1) if `tools` was NOT explicitly passed, defaults it to
    get_role_tools(role) instead of the full DECISION_TOOLS set; (2) is
    passed through to compose_decision_prompt for that role's mission-line
    framing (only when prompt_override is None — a prompt_override caller,
    i.e. pricing_cycle.py, already built its own prompt text and only wants
    role for tagging + the tool-scoping in (1), which it already does
    explicitly via `tools=`). Every AgentActionDB row this creates gets
    role.name (or None) written to its own `role` column regardless of
    which of these two effects actually applied, so a pricing_cycle call
    that already passed explicit `tools=` still gets correctly tagged.

    _escalation_depth/_escalation_prefix are internal-only (never set by an
    external caller) — used exclusively by this function's own recursive
    self-call when a role escalates to another (see the ESCALATE_TOOL_NAME
    branch below). _escalation_depth > 0 strips the escalation tool from
    the inner call's own tool list regardless of what that role's own
    can_escalate_to is configured as, which is what makes the single-hop
    cap structural rather than a runtime-checked limit. _escalation_prefix
    is prepended to the inner call's final `reasoning` so the merchant sees
    both roles' reasoning on one card.
    """
    from sqlalchemy import select

    # Quantified per-role learning — computed here (moved ahead of the
    # pending-action gate; it used to run only after products/memory were
    # fetched) so BOTH the priority-arbitration gate below and the prompt/
    # context_snapshot use further down share this one fetch. role=None
    # callers (non-swarm) keep today's behavior byte-identical.
    from app.services.learning import load_role_learning, render_learned_stance, compute_effective_priority
    incoming_learning = None
    if role is not None:
        try:
            incoming_learning = await load_role_learning(merchant_id, role, db)
        except Exception as e:  # noqa: BLE001 — learning must never block a decision
            logger.warning("[decision] learning read failed for %s: %s", merchant_id, e)
    learned_stance = render_learned_stance(incoming_learning) if incoming_learning is not None else ""

    # Gate: only one pending action at a time per store.
    # A STALE pending action (older than the TTL) is dismissed here and now —
    # it was expiring anyway. A NON-stale one can still be outranked by a
    # higher-priority incoming signal (memory-informed priority arbitration,
    # reusing the same per-role learning computed above plus one lookup for
    # the existing action's own role). BUT that dismissal is DEFERRED: we only
    # record the intent (supersede_existing) here and actually retire the old
    # card down in the action-creation path, once a replacement really exists.
    # Dismissing a valid card at the gate and THEN having the new cycle
    # decline or get blocked would leave the merchant with a vanished card and
    # nothing in its place — so the two must commit together, or not at all.
    existing = await db.scalar(
        select(AgentActionDB)
        .where(AgentActionDB.merchant_id == merchant_id)
        .where(AgentActionDB.status == "pending")
    )
    superseded_prefix = ""
    supersede_existing = None  # a non-stale, lower-priority action to retire IFF a replacement is created
    if existing:
        ttl = _pending_ttl_for(existing.action_type)
        age_seconds = (int(time.time() * 1000) - existing.created_at) / 1000
        if age_seconds > ttl:
            # Stale — safe to dismiss immediately (unchanged from today).
            await _dismiss_pending_action(existing, merchant_id, db, redis, "signal_stale")
            await db.commit()
            logger.info(
                "[decision] auto-dismissed stale action %s (age: %.0fs, ttl: %ds) for %s",
                existing.id, age_seconds, ttl, merchant_id,
            )
        else:
            from app.services.qwen_roles import role_for_action_type, role_by_name
            existing_role = role_by_name(existing.role or role_for_action_type(existing.action_type))
            existing_learning = None
            if existing_role is not None:
                try:
                    existing_learning = await load_role_learning(merchant_id, existing_role, db)
                except Exception as e:  # noqa: BLE001 — learning must never block a decision
                    logger.warning("[decision] existing-role learning read failed for %s: %s", merchant_id, e)
            incoming_priority = (
                compute_effective_priority(role.default_priority, incoming_learning)
                if role is not None else 0
            )
            existing_priority = (
                compute_effective_priority(existing_role.default_priority, existing_learning)
                if existing_role is not None else 0
            )
            if incoming_priority <= existing_priority:
                logger.info(f"[decision] skipping cycle — pending action already exists for {merchant_id}")
                return None
            # Outranked — but hold the dismissal until the replacement is real.
            supersede_existing = existing
            superseded_prefix = (
                f"Superseded a pending {existing_role.name if existing_role else 'unclassified'} "
                f"action ({existing.action_type}) — this signal ranked higher priority."
            )

    merchant = await db.get(MerchantDB, merchant_id)
    if not merchant:
        return None

    brand_profile = await db.get(BrandProfileDB, merchant_id)
    brand_voice = "professional, friendly"
    mood = "balanced"
    brand_rules_summary = "maintain brand integrity"
    if brand_profile:
        gb = brand_profile.generated_brand or {}
        brand_voice = gb.get("brand", {}).get("brand_voice_profile", brand_voice)
        mood = gb.get("brand", {}).get("layout_variant", mood)
        guards = gb.get("guards", {})
        rules = guards.get("rules", [])
        brand_rules_summary = "; ".join(r.get("description", "") for r in rules[:3]) or brand_rules_summary

    products_result = await db.execute(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant_id)
        .where(ProductDB.is_active == True)
        .limit(10)
    )
    products = products_result.scalars().all()
    products_summary = ", ".join(
        f"{p.name} (${p.price}, stock: {p.stock})" for p in products
    ) or "no products yet"

    # Catalog-wide average price (not just the 10-row prompt sample) — the honest
    # basis for the grounded revenue estimate below.
    from sqlalchemy import func
    avg_price = float(await db.scalar(
        select(func.avg(ProductDB.price))
        .where(ProductDB.merchant_id == merchant_id)
        .where(ProductDB.is_active == True)
        .where(ProductDB.price > 0)
    ) or 0.0)

    # Pull prior-outcome memory and inject it — the cognitive loop closes here.
    from app.services.memory import get_memory, build_memory_context
    try:
        entries = await get_memory(merchant_id, db, redis)
    except Exception as e:  # noqa: BLE001 — memory must never block a decision
        logger.warning("[decision] memory read failed for %s: %s", merchant_id, e)
        entries = []
    memory_context = build_memory_context(entries)

    # learned_stance was already computed above (ahead of the pending-action
    # gate, so arbitration could use it too) — just fold it into the prompt here.
    memory_for_prompt = f"{memory_context}\n{learned_stance}".strip() if learned_stance else memory_context

    if prompt_override is not None:
        # A pricing cycle (run_pricing_cycle, pricing_cycle.py) builds its own
        # product-specific prompt via compose_pricing_prompt — the anomaly/
        # catalog-summary prompt shape here doesn't fit a single-product
        # repricing decision.
        prompt = prompt_override
    else:
        from app.services.profile import load_constraints
        constraints = await load_constraints(db, merchant_id)
        prompt = compose_decision_prompt(
            store_name=merchant.store_name,
            mood=mood,
            brand_voice=brand_voice,
            brand_rules_summary=brand_rules_summary,
            products_summary=products_summary,
            anomaly_description=anomaly_desc,
            memory_context=memory_for_prompt,
            max_discount_percent=constraints.max_discount_percent,
            role=role,
        )
    estimated_tokens = len(prompt) // 4  # rough char/4 heuristic for the terminal badge

    if tools is not None:
        effective_tools = tools
    elif role is not None:
        from app.services.qwen_roles import get_role_tools, ESCALATE_TOOL_NAME
        effective_tools = get_role_tools(role)
        if _escalation_depth > 0:
            effective_tools = [t for t in effective_tools if t["function"]["name"] != ESCALATE_TOOL_NAME]
    else:
        effective_tools = DECISION_TOOLS

    try:
        message = await _qwen_chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.5,
            timeout=45.0,
            tools=effective_tools,
            tool_choice="auto",
            merchant_id=merchant_id,
            step="decision_cycle",
        )
    except BrandGenerationError as e:
        logger.error(f"[decision] Qwen failed for {merchant_id}: {e}")
        return None

    # --- Parse tool-calling response ---
    if not isinstance(message, dict):
        logger.error("[decision] unexpected response type from _qwen_chat (tools mode)")
        return None

    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        # Qwen declined to propose an action (no anomaly worth acting on)
        logger.info(f"[decision] Qwen declined to call a tool for {merchant_id}")
        return None

    # Take the first tool call (we asked for ONE action)
    tc = tool_calls[0]
    tool_name = tc.get("function", {}).get("name", "")
    tool_args = parse_tool_args(tc.get("function", {}).get("arguments", "{}"))

    if not tool_name:
        logger.warning("[decision] tool call missing function name")
        return None

    from app.services.qwen_roles import ESCALATE_TOOL_NAME, ALL_ROLES
    if tool_name == ESCALATE_TOOL_NAME:
        target_role_name = tool_args.get("target_role", "")
        target_role = next((r for r in ALL_ROLES if r.name == target_role_name), None)
        allowed_names = {r.name for r in role.can_escalate_to} if role is not None else set()
        if role is None or target_role is None or target_role.name not in allowed_names:
            logger.warning(
                "[decision] escalation to '%s' not permitted for role %s — treating as declined",
                target_role_name, role.name if role else None,
            )
            return None
        escalation_reasoning = (tool_args.get("reasoning") or "")[:1000]
        logger.info(
            "[decision] %s escalating to %s for %s: %s",
            role.name, target_role.name, merchant_id, escalation_reasoning,
        )
        return await run_decision_cycle(
            merchant_id, anomaly_desc, db, redis,
            target_product_id=target_product_id, session_id=session_id,
            role=target_role, _escalation_depth=_escalation_depth + 1,
            _escalation_prefix=f"[Escalated from {role.name}] {escalation_reasoning}",
        )

    # Map tool name → AgentActionType enum
    action_type_enum = TOOL_TO_ACTION_TYPE.get(tool_name)
    if action_type_enum is None:
        logger.warning(f"[decision] unknown tool '{tool_name}', defaulting to flash_sale")
        action_type_enum = AgentActionType.FLASH_SALE

    # Layer 0 — structural safety, ahead of the interceptor. Reject tool-call
    # args that encode an impossible state (negative/>100% discount,
    # non-positive price, empty target id, self-contradictory merge) before
    # they can ever become an option card. This is distinct from the
    # interceptor below, which CLAMPS valid-but-aggressive values and
    # HARD-BLOCKS on live business state — here we reject the nonsensical,
    # the fingerprint of a hallucinated call, not a bold-but-legal move.
    try:
        tool_args = validate_tool_args(tool_name, tool_args)
    except ActionValidationError as e:
        logger.info(
            f"[decision] structural guard rejected {tool_name} for {merchant_id}: {e}"
        )
        from app.services import receipts
        await receipts.append_receipt(
            db, merchant_id, "blocked",
            note=f"{tool_name} rejected by structural guard: {e}",
        )
        await db.commit()
        return None

    reasoning = extract_reasoning(tool_args, message)
    reasoning_prefixes = [p for p in (superseded_prefix, _escalation_prefix) if p]
    if reasoning_prefixes:
        reasoning = "\n\n".join(reasoning_prefixes + [reasoning])

    # Use the product Qwen actually targeted, not just the first in the list.
    # propose_duplicate_merge uses keep_product_id, not product_id — same
    # fallback purpose (which product's name goes in the option card title).
    # A pricing cycle already knows exactly which product it's evaluating
    # (target_product_id) — that takes priority over parsing tool_args.
    # The DB fallback below is scoped ONLY to that explicit target_product_id
    # case: a pricing cycle's target may legitimately fall outside the
    # unordered top-10 `products` sample. When target_product_id is None
    # (every pre-existing caller, parsing tool_args instead), a miss against
    # the top-10 sample must leave targeted_product as None, exactly as it
    # did before this fallback existed — do NOT widen it to tool_args-parsed
    # ids, or every action type's cost_price/price/narrative silently changes
    # for merchants with >10 products.
    targeted_pid = target_product_id or tool_args.get("product_id") or tool_args.get("keep_product_id")
    targeted_product = None
    if targeted_pid:
        for p in products:
            if p.id == targeted_pid:
                targeted_product = p
                break
        # duplicate_merge's keep_product_id is authoritative for its target
        # (unlike a generically-parsed product_id, which could be Qwen
        # hallucination) — a top-10-sample miss must still resolve via DB,
        # or the narrative silently mislabels the card with products[0]'s
        # name instead of the actual duplicate-merge target.
        if targeted_product is None and (
            target_product_id is not None or tool_name == "propose_duplicate_merge"
        ):
            targeted_product = await db.get(ProductDB, targeted_pid)
            if targeted_product and targeted_product.merchant_id != merchant_id:
                targeted_product = None
    targeted_product_name = targeted_product.name if targeted_product else None
    product_name_for_narrative = targeted_product_name or (products[0].name if products else None)

    # A caller-supplied target_product_id is a verified, real product (the
    # caller looked it up in the DB before calling us) — it must win over
    # whatever product_id string Qwen's own tool call happened to contain.
    # Without this, the interceptor's cost/price check and the narrative both
    # correctly use the resolved product, but the PERSISTED payload still
    # carries Qwen's raw tool_args.product_id — so a hallucinated ID (Qwen
    # sees a full multi-product catalog and free-text description, not a
    # single scoped target) silently survives into the option card and can
    # never execute, since nothing else ever corrects it. See store_review.py
    # find_underperformer's real, verified id being discarded for the bug
    # this closes.
    if target_product_id is not None and targeted_product is not None and "product_id" in tool_args:
        tool_args = {**tool_args, "product_id": target_product_id}

    # Interceptor — real Layer 2/3 primitives, before this ever becomes an
    # option card. Declining here mirrors "Qwen declined to propose an action".
    from app.services import interceptor
    from app.services.profile import load_constraints
    constraints = await load_constraints(db, merchant_id)
    cost_price = targeted_product.cost_price if targeted_product else 0.0
    price = targeted_product.price if targeted_product else 0.0

    if action_type_enum == AgentActionType.PRICE_REBALANCE:
        baseline_price = targeted_product.baseline_price if targeted_product else price
        try:
            new_price = float(tool_args.get("new_price", price))
        except (TypeError, ValueError):
            new_price = price
        clamped_price, constraint_check, is_blocked = interceptor.enforce_price_rebalance(
            new_price, baseline_price=baseline_price, cost_price=cost_price,
            constraints=constraints, product_id=targeted_pid or "",
        )
        tool_args = dict(tool_args)
        tool_args["new_price"] = clamped_price
    else:
        tool_args, constraint_check, is_blocked = interceptor.enforce_action_discount(
            action_type_enum, tool_args,
            cost_price=cost_price, price=price, constraints=constraints,
            product_id=targeted_pid or "",
        )
    if session_id:
        tool_args = dict(tool_args)
        tool_args["session_id"] = session_id
    if is_blocked:
        logger.info(
            f"[decision] interceptor blocked {tool_name} for {merchant_id}: {constraint_check}"
        )
        from app.services import receipts
        await receipts.append_receipt(
            db, merchant_id, "blocked",
            note=f"{tool_name} blocked at decision time: {constraint_check}",
        )
        await db.commit()
        return None

    # Narrative fields templated from tool call + context — reflects the
    # already-clamped tool_args, so the option card shows the real number.
    narrative = narrative_from_tool(
        tool_name, tool_args, product_name_for_narrative, anomaly_desc, brand_voice
    )

    promo_id = f"ELEV_{merchant_id[:4].upper()}_{secrets.token_hex(3).upper()}"
    now = int(time.time() * 1000)

    # What Qwen actually saw when it made this call — the catalog snapshot,
    # prior-outcome memory, and discount ceiling that went into the prompt.
    # Captured verbatim (not reconstructed later) so the Decision Trace page
    # can show inputs alongside the reasoning output for a real audit trail,
    # not a summary. NOTE: for a prompt_override call (pricing cycle), the
    # actual prompt Qwen saw was compose_pricing_prompt's own single-product
    # framing, not this products_summary/memory_context pair — those are
    # still the real top-10 catalog snapshot and real memory read for this
    # cycle, just not verbatim what appeared in that specific prompt string.
    context_snapshot = {
        "products_summary": products_summary,
        "memory_context": memory_context,
        "learned_stance": learned_stance,
        "max_discount_percent": constraints.max_discount_percent,
        "avg_price": round(avg_price, 2),
    }

    # Ground the revenue estimate in the real anomaly magnitude + catalog price
    anomaly_count = _extract_count(anomaly_desc)
    est_gmv = grounded_gmv(action_type_enum.value, anomaly_count, avg_price)
    if est_gmv <= 0:
        est_gmv = float(tool_args.get("estimated_gmv", 0) or 0)

    # Graduated autonomy — PRICE_REBALANCE only. A trusted (merchant, product)
    # pair with a move already inside the interceptor-clamped range executes
    # immediately instead of waiting for merchant approval; every other
    # action type, and every PRICE_REBALANCE below the trust threshold or
    # outside the auto-apply band, takes the unchanged "pending" path.
    auto_trusted = False
    if action_type_enum == AgentActionType.PRICE_REBALANCE and targeted_product:
        from app.services.autopilot_trust import get_trust_state, should_auto_apply
        streak, auto_apply_enabled = await get_trust_state(merchant_id, targeted_pid, "price_rebalance", db)
        auto_trusted = should_auto_apply(
            streak, auto_apply_enabled, tool_args["new_price"], targeted_product.baseline_price, constraints,
        )

    # Deferred priority-supersede (decided at the gate): the replacement is
    # now real — Qwen proposed, the structural guard and interceptor passed,
    # and we're about to persist it — so it's finally safe to retire the
    # outranked card. It's dismissed here and committed in the SAME
    # transaction as the new action_db below (one await db.commit() covers
    # both), so the two are atomic: had the cycle declined or been blocked
    # anywhere above, this line is never reached and the old card survives.
    if supersede_existing is not None:
        await _dismiss_pending_action(
            supersede_existing, merchant_id, db, redis, "superseded_by_higher_priority"
        )

    action_db = AgentActionDB(
        id=str(uuid4()),
        merchant_id=merchant_id,
        promo_id=promo_id,
        action_type=action_type_enum.value,
        trigger=narrative["trigger"],
        reasoning=reasoning,
        context_snapshot=context_snapshot,
        role=role.name if role is not None else None,
        title=narrative["title"][:200],
        description=narrative["description"][:500],
        estimated_gmv=est_gmv,
        estimated_confidence=0.75,  # tool calling = high confidence in structured output
        payload=tool_args,  # tool args become the execution payload directly
        brand_check=narrative["brand_check"][:500],
        constraint_check=constraint_check,
        status="executed" if auto_trusted else "pending",
        created_at=now,
        approved_at=now if auto_trusted else None,
        executed_at=now if auto_trusted else None,
        merchant_behavior="auto_trusted" if auto_trusted else None,
        trigger_description=anomaly_desc[:1000],
    )
    db.add(action_db)
    await db.commit()
    await db.refresh(action_db)

    from app.services import receipts
    if auto_trusted:
        from app.routers.agent import _execute_payload, _broadcast_state_update
        applied = await _execute_payload(action_db, db)
        if not applied:
            # State drifted unsafe between the interceptor check above and
            # execution (rare, defense-in-depth) — fall back to a normal
            # gated card instead of silently losing the proposal.
            action_db.status = "pending"
            action_db.approved_at = None
            action_db.executed_at = None
            action_db.merchant_behavior = None
            await db.commit()
            await receipts.append_receipt(db, merchant_id, "proposed", action_row=action_db)
        else:
            await db.commit()
            await receipts.append_receipt(db, merchant_id, "executed", action_row=action_db)
            await _broadcast_state_update(merchant_id)
            # The merchant explicitly opted into this via the auto-apply
            # toggle, but "opted in" isn't the same as "invisible" — this is
            # the one path that skips the approval card entirely, so it's
            # also the one that most needs an explicit FYI. Belt-and-suspenders
            # with state_updated above: that morphs the storefront, this
            # tells the terminal WHY.
            try:
                from app.models.schemas import WSMessage
                await manager.push_to_terminal(
                    merchant_id,
                    WSMessage(
                        event=WSEventType.ACTION_AUTO_EXECUTED,
                        payload={"action": {
                            "id": action_db.id,
                            "action_type": action_db.action_type,
                            "title": action_db.title,
                            "description": action_db.description,
                            "reasoning": action_db.reasoning,
                            "role": action_db.role,
                            "payload": action_db.payload,
                        }},
                        merchant_id=merchant_id,
                        timestamp=int(time.time() * 1000),
                    ),
                )
            except Exception as e:  # noqa: BLE001 — a missed FYI push must never break execution
                logger.warning("[decision] auto-executed WS push failed for %s: %s", action_db.id, e)
    else:
        await receipts.append_receipt(db, merchant_id, "proposed", action_row=action_db)
    await db.commit()

    action = AgentAction(
        id=action_db.id,
        merchant_id=action_db.merchant_id,
        promo_id=action_db.promo_id,
        action_type=AgentActionType(action_db.action_type),
        trigger=action_db.trigger,
        role=action_db.role,
        title=action_db.title,
        description=action_db.description,
        estimated_gmv=action_db.estimated_gmv,
        estimated_confidence=action_db.estimated_confidence,
        payload=action_db.payload,
        brand_check=action_db.brand_check,
        constraint_check=action_db.constraint_check,
        reasoning=action_db.reasoning,
        status=AgentActionStatus(action_db.status),
        created_at=action_db.created_at,
    )

    # Push to merchant terminal via WebSocket — include real cost data
    from app.models.schemas import WSMessage
    usage_summary = {}
    try:
        from app.services.brand import get_usage_summary
        usage_summary = await get_usage_summary(merchant_id)
    except Exception:
        pass  # cost tracking must never block the decision push

    await manager.push_to_terminal(
        merchant_id,
        WSMessage(
            event=WSEventType.AGENT_ACTION,
            payload={
                "action": action.model_dump(),
                "estimated_tokens": estimated_tokens,
                "memory_count": len(entries),
                "usage": usage_summary,
            },
            merchant_id=merchant_id,
            timestamp=now,
        ),
    )

    logger.info(f"[decision] fired {action.action_type} action {action.id} for {merchant_id}")
    return action
