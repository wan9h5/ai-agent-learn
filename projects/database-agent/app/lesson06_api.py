"""S2-03: FastAPI endpoint with normalized model error responses."""

import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.lesson05 import DatabaseQueryIntent
from app.lesson06 import (
    ModelCallError,
    ModelConfigurationError,
    ReliableQueryService,
    build_service,
    http_status_for_error,
    public_error_payload,
)


logger = logging.getLogger(__name__)
app = FastAPI(title="Database Agent - S2-03")


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message 不能为空。")
        return value


def get_service() -> ReliableQueryService:
    return build_service()


ServiceDep = Annotated[ReliableQueryService, Depends(get_service)]


@app.exception_handler(ModelCallError)
async def handle_model_call_error(
    request: Request,
    exc: ModelCallError,
) -> JSONResponse:
    logger.warning(
        "model_call_failed code=%s attempts=%s status=%s",
        exc.category.value,
        exc.attempts,
        exc.status_code,
    )
    return JSONResponse(
        status_code=http_status_for_error(exc.category),
        content=public_error_payload(exc),
    )


@app.exception_handler(ModelConfigurationError)
async def handle_model_configuration_error(
    request: Request,
    exc: ModelConfigurationError,
) -> JSONResponse:
    logger.error("model_configuration_invalid")
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "model_configuration_error",
                "message": str(exc),
            }
        },
    )


@app.post("/intent", response_model=DatabaseQueryIntent)
def extract_intent(
    body: IntentRequest,
    service: ServiceDep,
) -> DatabaseQueryIntent:
    return service.extract(body.message)
