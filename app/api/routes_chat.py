from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models.user import User
from app.services.chat_service import ChatServiceError, ask_gemini

router = APIRouter(prefix="/api/chat", tags=["chat"])
settings = get_settings()


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, _: User = Depends(get_current_user)) -> ChatResponse:
    if not settings.CHATBOT_ENABLED:
        raise HTTPException(503, "The support chatbot is currently disabled.")

    try:
        reply = await ask_gemini(
            payload.message,
            history=[turn.model_dump() for turn in payload.history],
        )
    except ChatServiceError as exc:
        raise HTTPException(502, str(exc)) from exc

    return ChatResponse(reply=reply)


@router.get("/status")
async def chat_status() -> dict:
    return {
        "enabled": settings.CHATBOT_ENABLED,
        "configured": bool(settings.GEMINI_API_KEY),
        "model": settings.GEMINI_MODEL,
    }
