import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.ws_manager import manager
from app.models.schemas import WSMessage, WSEventType
from app.services import delta as delta_svc
from app.services.interceptor import validate_decision
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/terminal/{merchant_id}")
async def terminal_ws(ws: WebSocket, merchant_id: str):
    """
    Merchant command terminal connection.
    
    Receives: approve_action, reject_action, stage_preview, rollback
    Sends:    decision_ready, action_clamped, action_blocked, state_updated
    """
    await manager.connect_terminal(merchant_id, ws)

    # Merchant profile must be sent as first message after connect
    profile = None

    try:
        while True:
            raw = await ws.receive_text()
            msg = WSMessage.model_validate_json(raw)

            # ── First message must be the business profile ────────────────────
            if msg.event == WSEventType.APPROVE_ACTION and profile is None:
                await ws.send_text(WSMessage(
                    event=WSEventType.ACTION_BLOCKED,
                    payload={"error": "Send business profile first"},
                    merchant_id=merchant_id,
                    timestamp=_now(),
                ).model_dump_json())
                continue

            # ── Merchant approves an option card ──────────────────────────────
            if msg.event == WSEventType.APPROVE_ACTION:
                action_id = msg.payload["action_id"]
                patches_raw = msg.payload["patches"]

                current_state = await delta_svc.load_state(merchant_id)
                if not current_state:
                    continue

                from app.models.schemas import JsonPatch
                patches = [JsonPatch.model_validate(p) for p in patches_raw]

                new_state, execution = await delta_svc.execute_delta(
                    merchant_id, action_id, patches, current_state
                )

                # Push updated state to BOTH terminal and storefront
                update_msg = WSMessage(
                    event=WSEventType.STATE_UPDATED,
                    payload={
                        "state": json.loads(new_state.model_dump_json()),
                        "execution": json.loads(execution.model_dump_json()),
                    },
                    merchant_id=merchant_id,
                    timestamp=_now(),
                )
                await manager.push_to_all(merchant_id, update_msg)

            # ── Merchant stages a preview (sandbox) ───────────────────────────
            elif msg.event == WSEventType.STAGE_PREVIEW:
                from app.models.schemas import JsonPatch
                patches = [JsonPatch.model_validate(p) for p in msg.payload["patches"]]
                current_state = await delta_svc.load_state(merchant_id)
                if not current_state:
                    continue

                preview = delta_svc.stage_preview(current_state, patches)

                await ws.send_text(WSMessage(
                    event=WSEventType.STATE_UPDATED,
                    payload={
                        "state": json.loads(preview.model_dump_json()),
                        "staged": True,
                    },
                    merchant_id=merchant_id,
                    timestamp=_now(),
                ).model_dump_json())

            # ── Merchant triggers rollback ─────────────────────────────────────
            elif msg.event == WSEventType.ROLLBACK:
                prev_state = await delta_svc.rollback_last(merchant_id)
                if prev_state:
                    rollback_msg = WSMessage(
                        event=WSEventType.STATE_UPDATED,
                        payload={
                            "state": json.loads(prev_state.model_dump_json()),
                            "rollback": True,
                        },
                        merchant_id=merchant_id,
                        timestamp=_now(),
                    )
                    await manager.push_to_all(merchant_id, rollback_msg)

    except WebSocketDisconnect:
        manager.disconnect_terminal(merchant_id, ws)
        logger.info(f"[WS] Terminal disconnected: {merchant_id}")


@router.websocket("/ws/storefront/{merchant_id}")
async def storefront_ws(ws: WebSocket, merchant_id: str):
    """
    Storefront connection — customers browsing the live store.

    Receives: customer_event (view, hover, cart_add, purchase, abandon)
    Sends:    state_updated (hot-reloads UI immediately on delta)
    """
    await manager.connect_storefront(merchant_id, ws)

    try:
        # Send current state on connect so storefront hydrates immediately
        current_state = await delta_svc.load_state(merchant_id)
        if current_state:
            await ws.send_text(WSMessage(
                event=WSEventType.STATE_UPDATED,
                payload={"state": json.loads(current_state.model_dump_json())},
                merchant_id=merchant_id,
                timestamp=_now(),
            ).model_dump_json())

        while True:
            raw = await ws.receive_text()
            msg = WSMessage.model_validate_json(raw)

            # ── Customer event flows into telemetry ───────────────────────────
            if msg.event == WSEventType.CUSTOMER_EVENT:
                from app.models.schemas import CustomerEvent
                from app.services.telemetry import record_event
                event = CustomerEvent.model_validate(msg.payload["event"])
                await record_event(merchant_id, event)

    except WebSocketDisconnect:
        manager.disconnect_storefront(merchant_id, ws)
        logger.info(f"[WS] Storefront disconnected: {merchant_id}")


def _now() -> int:
    return int(time.time() * 1000)
