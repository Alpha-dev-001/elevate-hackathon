import asyncio
import json
from fastapi import WebSocket
from app.models.schemas import WSMessage, WSEventType
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages all active WebSocket connections.
    
    Two connection pools:
    - terminal:  merchant command interfaces (receives decisions, sends approvals)
    - storefront: customer-facing stores (receives state updates)
    
    Each pool is scoped by merchant_id so pushes are isolated.
    """

    def __init__(self):
        # merchant_id → list of active terminal connections
        self.terminal_connections: dict[str, list[WebSocket]] = {}
        # merchant_id → list of active storefront connections
        self.storefront_connections: dict[str, list[WebSocket]] = {}

    # ── Connection lifecycle ───────────────────────────────────────────────────

    async def connect_terminal(self, merchant_id: str, ws: WebSocket):
        await ws.accept()
        self.terminal_connections.setdefault(merchant_id, []).append(ws)
        logger.info(f"[WS] Terminal connected: {merchant_id} ({len(self.terminal_connections[merchant_id])} active)")

    async def connect_storefront(self, merchant_id: str, ws: WebSocket):
        await ws.accept()
        self.storefront_connections.setdefault(merchant_id, []).append(ws)
        logger.info(f"[WS] Storefront connected: {merchant_id}")

    def disconnect_terminal(self, merchant_id: str, ws: WebSocket):
        connections = self.terminal_connections.get(merchant_id, [])
        if ws in connections:
            connections.remove(ws)
        logger.info(f"[WS] Terminal disconnected: {merchant_id}")

    def disconnect_storefront(self, merchant_id: str, ws: WebSocket):
        connections = self.storefront_connections.get(merchant_id, [])
        if ws in connections:
            connections.remove(ws)
        logger.info(f"[WS] Storefront disconnected: {merchant_id}")

    # ── Push to terminal (merchant sees option cards) ──────────────────────────

    async def push_to_terminal(self, merchant_id: str, message: WSMessage):
        """Push a decision or alert to all merchant terminal connections."""
        connections = self.terminal_connections.get(merchant_id, [])
        if not connections:
            logger.warning(f"[WS] No terminal connections for {merchant_id}")
            return
        await self._broadcast(connections, message)

    # ── Push to storefront (customers see live state) ──────────────────────────

    async def push_to_storefront(self, merchant_id: str, message: WSMessage):
        """Push a state update to all storefront connections."""
        connections = self.storefront_connections.get(merchant_id, [])
        await self._broadcast(connections, message)

    # ── Push to both surfaces ─────────────────────────────────────────────────

    async def push_to_all(self, merchant_id: str, message: WSMessage):
        await asyncio.gather(
            self.push_to_terminal(merchant_id, message),
            self.push_to_storefront(merchant_id, message),
        )

    # ── Internal broadcast ────────────────────────────────────────────────────

    async def _broadcast(self, connections: list[WebSocket], message: WSMessage):
        payload = message.model_dump_json()
        dead = []
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.error(f"[WS] Send failed: {e}")
                dead.append(ws)
        # Clean up dead connections
        for ws in dead:
            if ws in connections:
                connections.remove(ws)

    # ── Stats ──────────────────────────────────────────────────────────────────

    def active_connections(self, merchant_id: str) -> dict:
        return {
            "terminal": len(self.terminal_connections.get(merchant_id, [])),
            "storefront": len(self.storefront_connections.get(merchant_id, [])),
        }


# Singleton — shared across the app
manager = ConnectionManager()
