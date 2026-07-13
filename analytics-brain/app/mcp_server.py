"""
Elevate Autopilot — MCP (Model Context Protocol) Server

Exposes the autonomous commerce agent to any MCP-compatible client
(Claude Desktop, Cursor, or another AI agent) so external systems can:

  - Read the current store state
  - Trigger a decision cycle with a custom anomaly description
  - Approve or dismiss pending agent actions
  - Read the recent action feed

Run standalone:
    python -m app.mcp_server

Or via FastMCP CLI:
    fastmcp run app/mcp_server.py:mcp
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.redis import get_redis, Keys
from app.core.security import decode_token
from app.models.db_models import AgentActionDB, MerchantDB
from app.models.schemas import AgentActionType, AgentActionStatus

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Elevate Autopilot",
    instructions=(
        "Tools for driving the Elevate autonomous commerce agent. "
        "Use elevate_get_store_state to inspect the live store, "
        "elevate_run_decision_cycle to trigger Qwen's decision-making from "
        "a described anomaly, elevate_run_store_review to trigger it "
        "proactively from real catalog performance instead (no anomaly "
        "needed), elevate_run_duplicate_scan to check for duplicate "
        "product listings specifically, and elevate_approve_action / "
        "elevate_dismiss_action to respond to pending agent proposals. "
        "Approve/dismiss RELAY a merchant's own decision — they require the "
        "merchant's real session token and cannot be used by an agent to "
        "approve or dismiss on its own authority."
    ),
)


async def _get_db_session():
    """Create a standalone DB session (outside FastAPI dependency injection)."""
    factory = get_session_factory()
    return factory()


def _action_row_to_dict(row: AgentActionDB) -> dict[str, Any]:
    return {
        "id": row.id,
        "merchant_id": row.merchant_id,
        "promo_id": row.promo_id,
        "action_type": row.action_type,
        "trigger": row.trigger,
        "title": row.title,
        "description": row.description,
        "estimated_gmv": row.estimated_gmv,
        "estimated_confidence": row.estimated_confidence,
        "payload": row.payload,
        "brand_check": row.brand_check,
        "reasoning": row.reasoning,
        "status": row.status,
        "created_at": row.created_at,
        "approved_at": row.approved_at,
        "executed_at": row.executed_at,
    }


def _verify_merchant_token(merchant_session_token: str | None, owner_merchant_id: str) -> str | None:
    """Verify the caller holds the owning merchant's own session token.

    Returns an error message if missing/invalid/expired/wrong-store; None if
    it checks out. This is the actual gate: it stops an agent from approving
    or dismissing on its own authority — it can only relay a decision a human
    already authenticated for via the terminal (the same elevate_session JWT
    issued at login), never invent one.
    """
    if not merchant_session_token:
        return (
            "merchant_session_token is required. This tool relays a human's "
            "own decision — it does not grant one on the agent's authority."
        )
    try:
        token_merchant_id = decode_token(merchant_session_token)
    except HTTPException as e:
        return str(e.detail)
    if token_merchant_id != owner_merchant_id:
        return "This session token belongs to a different store than the one that owns this action."
    return None


async def _resolve_merchant(db, merchant_id_or_slug: str) -> str | None:
    """Resolve either a merchant_id or a store slug to a merchant_id."""
    # Try direct ID first
    merchant = await db.get(MerchantDB, merchant_id_or_slug)
    if merchant:
        return merchant.id
    # Try slug lookup
    merchant = await db.scalar(
        select(MerchantDB).where(MerchantDB.slug == merchant_id_or_slug)
    )
    return merchant.id if merchant else None


# ─── Tool 1: Get Store State ─────────────────────────────────────────────────


@mcp.tool()
async def elevate_get_store_state(merchant_id: str) -> str:
    """Get the current live state of an Elevate store.

    Returns the full SystemState: products, active promos, layout config,
    recovery offers, and version info. Accepts a merchant_id or store slug.

    Args:
        merchant_id: The merchant's UUID or store slug.
    """
    async with await _get_db_session() as db:
        mid = await _resolve_merchant(db, merchant_id)
        if not mid:
            return json.dumps({"error": "Store not found", "merchant_id": merchant_id})

    redis = await get_redis()
    raw = await redis.get(Keys.system_state(mid))
    if not raw:
        return json.dumps({
            "merchant_id": mid,
            "status": "no_state",
            "message": "Store has not been published yet. No live state exists.",
        })

    state = json.loads(raw)

    # Also grab pending actions so the caller sees the full picture
    pending_raw = await redis.get(Keys.pending_actions(mid))
    pending = json.loads(pending_raw) if pending_raw else []

    return json.dumps({
        "merchant_id": mid,
        "state": state,
        "pending_actions": pending if isinstance(pending, list) else [pending],
    }, indent=2, default=str)


# ─── Tool 2: Run Decision Cycle ──────────────────────────────────────────────


@mcp.tool()
async def elevate_run_decision_cycle(
    merchant_id: str,
    anomaly_description: str,
) -> str:
    """Trigger a Qwen decision cycle for an Elevate store.

    The agent analyzes the described anomaly (e.g. 'velocity spike: 24 views
    on product X in 30 seconds' or 'cart abandon surge: 5 abandons') and
    proposes one action for the merchant to review.

    Args:
        merchant_id: The merchant's UUID or store slug.
        anomaly_description: Description of the behavior anomaly to act on.
    """
    async with await _get_db_session() as db:
        mid = await _resolve_merchant(db, merchant_id)
        if not mid:
            return json.dumps({"error": "Store not found", "merchant_id": merchant_id})

        from app.services.decision_engine import run_decision_cycle

        redis = await get_redis()
        action = await run_decision_cycle(mid, anomaly_description, db, redis)

        if action is None:
            return json.dumps({
                "merchant_id": mid,
                "result": "no_action",
                "message": (
                    "Decision cycle completed but no action was proposed. "
                    "This can mean: a pending action already exists (one at a time), "
                    "Qwen declined to act, or the store has no products."
                ),
            })

        return json.dumps({
            "merchant_id": mid,
            "result": "action_proposed",
            "action": action.model_dump(),
        }, indent=2, default=str)


# ─── Tool 2b: Run Proactive Store Review ─────────────────────────────────────


@mcp.tool()
async def elevate_run_store_review(merchant_id: str) -> str:
    """Trigger Elevate's proactive store review for a store.

    Unlike elevate_run_decision_cycle (which needs a described anomaly),
    this scans real catalog performance itself: products with real view
    interest (Redis) but zero completed orders (Postgres) in the review
    window. If one stands out, it runs through the same decision cycle as
    a velocity spike or cart-abandon surge — same tools, same interceptor,
    same memory loop. Returns no_action when the catalog looks healthy;
    that is a correct, quiet outcome, not a failure.

    Args:
        merchant_id: The merchant's UUID or store slug.
    """
    async with await _get_db_session() as db:
        mid = await _resolve_merchant(db, merchant_id)
        if not mid:
            return json.dumps({"error": "Store not found", "merchant_id": merchant_id})

        from app.services.store_review import run_store_review

        redis = await get_redis()
        action = await run_store_review(mid, db, redis)

        if action is None:
            return json.dumps({
                "merchant_id": mid,
                "result": "no_action",
                "message": (
                    "No underperformer found — every viewed product either "
                    "has orders or hasn't cleared the minimum view threshold, "
                    "or a decision is already pending for this store."
                ),
            })

        return json.dumps({
            "merchant_id": mid,
            "result": "action_proposed",
            "action": action.model_dump(),
        }, indent=2, default=str)


# ─── Tool 3: Approve Action ─────────────────────────────────────────────────


@mcp.tool()
async def elevate_approve_action(action_id: str, merchant_session_token: str) -> str:
    """Relay a merchant's own approval decision, executing its payload on the store.

    This does NOT let an agent decide on the merchant's behalf. It requires
    the owning merchant's real session token (the same elevate_session JWT
    minted at login) as proof a human already approved this in the terminal.
    Call elevate_get_store_state / elevate_get_terminal_feed to read and
    reason about pending actions freely — only this call needs the token,
    because only this call changes the live store.

    Args:
        action_id: The UUID of the pending action to approve.
        merchant_session_token: The owning merchant's elevate_session JWT,
            proving this approval is being relayed on behalf of an
            authenticated human, not decided autonomously by the caller.
    """
    async with await _get_db_session() as db:
        row = await db.get(AgentActionDB, action_id)
        if not row:
            return json.dumps({"error": "Action not found", "action_id": action_id})

        auth_error = _verify_merchant_token(merchant_session_token, row.merchant_id)
        if auth_error:
            return json.dumps({"error": auth_error, "action_id": action_id})

        if row.status != "pending":
            return json.dumps({
                "error": f"Action is already {row.status}",
                "action_id": action_id,
            })

        now = int(time.time() * 1000)
        row.status = "approved"
        row.approved_at = now
        row.merchant_behavior = "approved_via_mcp"

        # Execute the payload (promo registration, layout morph, etc.)
        from app.routers.agent import _execute_payload, _broadcast_state_update
        applied = await _execute_payload(row, db)

        row.status = "executed" if applied else "blocked_at_execution"
        row.executed_at = int(time.time() * 1000) if applied else None
        await db.commit()

        # Best-effort WS broadcast (only works if FastAPI is running)
        try:
            await _broadcast_state_update(row.merchant_id)
        except Exception:
            pass  # MCP server may not share WS connections with FastAPI

        if applied:
            # Schedule outcome observation
            try:
                from app.services.outcome_observer import schedule_observation
                schedule_observation(row.id, None, redis=await get_redis())
            except Exception:
                pass

        return json.dumps({
            "result": "approved_and_executed" if applied else "blocked_at_execution",
            "action": _action_row_to_dict(row),
        }, indent=2, default=str)


# ─── Tool 4: Dismiss Action ──────────────────────────────────────────────────


@mcp.tool()
async def elevate_dismiss_action(action_id: str, merchant_session_token: str) -> str:
    """Relay a merchant's own dismissal of a pending agent action (not executed).

    Same authority rule as elevate_approve_action: requires the owning
    merchant's real session token, because a dismissal still mutates the
    action's status and feeds Qwen's rejection memory — it must reflect a
    human's decision, not the calling agent's.

    Qwen still learns from the dismissal via the memory system —
    the outcome observer records the merchant's rejection.

    Args:
        action_id: The UUID of the pending action to dismiss.
        merchant_session_token: The owning merchant's elevate_session JWT.
    """
    async with await _get_db_session() as db:
        row = await db.get(AgentActionDB, action_id)
        if not row:
            return json.dumps({"error": "Action not found", "action_id": action_id})

        auth_error = _verify_merchant_token(merchant_session_token, row.merchant_id)
        if auth_error:
            return json.dumps({"error": auth_error, "action_id": action_id})

        row.status = "dismissed"
        row.merchant_behavior = "dismissed_via_mcp"
        await db.commit()

        # Record the outcome so Qwen learns from the rejection
        try:
            from app.services.outcome_observer import observe_outcome
            await observe_outcome(row.id, db, await get_redis(), behavior="dismissed")
        except Exception:
            pass

        return json.dumps({
            "result": "dismissed",
            "action": _action_row_to_dict(row),
        }, indent=2, default=str)


# ─── Tool 5: Get Terminal Feed ───────────────────────────────────────────────


@mcp.tool()
async def elevate_get_terminal_feed(merchant_id: str, limit: int = 10) -> str:
    """Get recent agent actions and their statuses for an Elevate store.

    Returns the action history: proposed, approved, executed, dismissed.
    This is the audit trail of what the autonomous agent has been doing.

    Args:
        merchant_id: The merchant's UUID or store slug.
        limit: Maximum number of actions to return (default 10).
    """
    async with await _get_db_session() as db:
        mid = await _resolve_merchant(db, merchant_id)
        if not mid:
            return json.dumps({"error": "Store not found", "merchant_id": merchant_id})

        result = await db.execute(
            select(AgentActionDB)
            .where(AgentActionDB.merchant_id == mid)
            .order_by(AgentActionDB.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()

        return json.dumps({
            "merchant_id": mid,
            "count": len(rows),
            "actions": [_action_row_to_dict(r) for r in rows],
        }, indent=2, default=str)


# ─── Tool 6: Run Duplicate Scan ──────────────────────────────────────────────


@mcp.tool()
async def elevate_run_duplicate_scan(merchant_id: str) -> str:
    """Trigger Elevate's duplicate-detection scan for a store.

    Checks for duplicate product listings — first a free exact-image-URL
    match, then (only if that finds nothing) one narrow Qwen call for
    semantic duplicates (same item, different photos). All-Qwen-generated
    exact-URL duplicates are silently auto-resolved with no card; a
    merchant-written or semantic duplicate group runs through the same
    decision cycle as every other trigger — same tools, same interceptor,
    same memory loop. Returns no_action when the catalog looks clean or a
    decision is already pending; that is a correct, quiet outcome, not a
    failure.

    Args:
        merchant_id: The merchant's UUID or store slug.
    """
    async with await _get_db_session() as db:
        mid = await _resolve_merchant(db, merchant_id)
        if not mid:
            return json.dumps({"error": "Store not found", "merchant_id": merchant_id})

        from app.services.duplicate_scan import run_duplicate_scan

        redis = await get_redis()
        action = await run_duplicate_scan(mid, db, redis)

        if action is None:
            return json.dumps({
                "merchant_id": mid,
                "result": "no_action",
                "message": (
                    "No duplicate group found — the catalog looks clean, "
                    "the only duplicates found were auto-resolved silently, "
                    "the best candidate is currently suppressed after a "
                    "recent dismissal, or a decision is already pending "
                    "for this store."
                ),
            })

        return json.dumps({
            "merchant_id": mid,
            "result": "action_proposed",
            "action": action.model_dump(),
        }, indent=2, default=str)


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
