import json
from typing import List
from fastapi import WebSocket, WebSocketDisconnect


class TelemetryHub:
    """
    Manages active dashboard WebSocket connections and broadcasts real-time telemetry events.
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event_type: str, data: dict):
        if not self.active_connections:
            return

        payload = json.dumps({
            "event_type": event_type,
            "data": data
        })

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                disconnected.append(connection)

        for dead_conn in disconnected:
            self.disconnect(dead_conn)


telemetry_hub = TelemetryHub()
