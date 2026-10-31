"""Local FastAPI adapter for S1-03; conversations are stateless here."""

import json
import logging
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.lesson03 import QueryIntent, build_model, chat_messages, extract_intent, stream_text

app = FastAPI(title="Database Agent - S1-03")
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)


class IntentRequest(ChatRequest):
    method: Literal["json_schema", "function_calling"] = "json_schema"


def get_model() -> ChatOpenAI:
    try:
        return build_model()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="模型配置不完整") from exc


ModelDep = Annotated[ChatOpenAI, Depends(get_model)]


def sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
def chat_stream(body: ChatRequest, model: ModelDep):
    def events():
        try:
            for text in stream_text(model, chat_messages(body.message)):
                yield sse("delta", {"text": text})
        except Exception as exc:
            logger.warning("stream failed: %s", type(exc).__name__)
            yield sse("error", {"message": "生成中断，本次回答未完成"})
            return
        yield sse("done", {})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/intent", response_model=QueryIntent)
def intent(body: IntentRequest, model: ModelDep):
    try:
        return extract_intent(model, body.message, body.method)
    except Exception as exc:
        logger.warning("intent failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="模型未返回可用的查询意图") from exc
