import json
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections and broadcasts updates to all clients."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, event_type: str, data: dict):
        message = json.dumps({"type": event_type, "data": data})
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.active_connections.remove(conn)

    async def broadcast_spot_start(self, spot_start: dict):
        await self.broadcast("spot_start_alert", spot_start)

    async def broadcast_lineup_update(self, lineup: dict):
        await self.broadcast("lineup_update", lineup)

    async def broadcast_projections(self, projections: list[dict]):
        await self.broadcast("projections_update", {"projections": projections})

    async def broadcast_injury(self, injury: dict):
        await self.broadcast("injury_update", injury)


manager = ConnectionManager()
