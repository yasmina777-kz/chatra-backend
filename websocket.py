import json
from fastapi import APIRouter, WebSocket, Query, HTTPException
from starlette.websockets import WebSocketDisconnect
from sqlalchemy.orm import Session
from db import SessionLocal
from security import decode_token
from crud import users as crud_users

router = APIRouter()


connections: dict[int, list[WebSocket]] = {}


async def _authenticate(token: str) -> int | None:
    """Verify JWT and return user_id, or None if invalid."""
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
        if not user_id:
            return None
        db: Session = SessionLocal()
        try:
            user = crud_users.get_user_by_id(db, user_id)
            if not user or not user.is_active:
                return None
            return user_id
        finally:
            db.close()
    except Exception:
        return None


@router.websocket("/ws/{chat_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    chat_id: int,
    token: str = Query(...),   # ?token=<jwt>
):
    user_id = await _authenticate(token)
    if not user_id:
        await websocket.close(code=4001)   # 4001 = Unauthorized
        return

    await websocket.accept()
    connections.setdefault(chat_id, []).append(websocket)

    try:
        while True:
            raw = await websocket.receive_text()

            # Broadcast to all members of the chat
            dead = []
            for conn in connections.get(chat_id, []):
                try:
                    await conn.send_text(raw)
                except Exception:
                    dead.append(conn)

            # Clean up disconnected sockets
            for d in dead:
                try:
                    connections[chat_id].remove(d)
                except ValueError:
                    pass

    except WebSocketDisconnect:
        try:
            connections[chat_id].remove(websocket)
        except (ValueError, KeyError):
            pass
