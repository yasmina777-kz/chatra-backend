import os
import httpx
from typing import List, Optional, Union, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from deps import get_current_user
from db import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/ai", tags=["AI"])

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o-mini"   # supports vision


class ChatMessage(BaseModel):
    role: str                          # "system" | "user" | "assistant"
    content: Union[str, List[Any]]     # str for text, list for vision


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    max_tokens: int = 2000
    temperature: float = 0.7
    class_id: Optional[int] = None


class ChatResponse(BaseModel):
    content: str


def _serialize_message(m: ChatMessage) -> dict:
    """Convert ChatMessage → OpenAI-compatible dict."""
    if isinstance(m.content, str):
        return {"role": m.role, "content": m.content}
    # Vision / multimodal content (list of content blocks)
    return {"role": m.role, "content": m.content}


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    body: ChatRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured. Please set OPENAI_API_KEY on the server.",
        )

    if not body.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")

    max_tokens = min(body.max_tokens, 4000)

    # Detect if any message contains an image → use vision-capable model
    has_vision = any(
        isinstance(m.content, list) for m in body.messages
    )
    model = OPENAI_MODEL  # gpt-4o-mini handles both text and vision

    payload = {
        "model": model,
        "messages": [_serialize_message(m) for m in body.messages],
        "max_tokens": max_tokens,
        "temperature": body.temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                OPENAI_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=payload,
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI service timed out")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"AI service unreachable: {e}")

    if not resp.is_success:
        try:
            err = resp.json()
            msg = err.get("error", {}).get("message", f"OpenAI error {resp.status_code}")
        except Exception:
            msg = f"OpenAI error {resp.status_code}"
        raise HTTPException(status_code=502, detail=msg)

    data = resp.json()
    content = data["choices"][0]["message"]["content"]

    # ── Log token usage ───────────────────────────────────────────────────────
    try:
        usage = data.get("usage", {})
        from models import AiUsageLog
        log = AiUsageLog(
            user_id=current_user.id,
            class_id=body.class_id,
            endpoint="chat_vision" if has_vision else "chat",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
        db.add(log)
        db.commit()
    except Exception:
        pass

    return ChatResponse(content=content)
