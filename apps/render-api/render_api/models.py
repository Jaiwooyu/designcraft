from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RenderOptions(BaseModel):
    format: Literal["png", "pdf", "both"] = "both"
    scale: float = Field(default=1, ge=0.1, le=4, allow_inf_nan=False)
    fallback_font: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("fallback_font")
    @classmethod
    def font_name(cls, value):
        if value is not None and (
            value.startswith("--") or not value.strip() or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("fallback_font must be a font family name")
        return value


class Artifact(BaseModel):
    name: str
    media_type: str
    size: int
    download_url: str


class RenderJob(BaseModel):
    id: str
    status: Literal[
        "uploading", "queued", "running", "cancelling", "succeeded", "failed", "cancelled"
    ]
    created_at: datetime
    updated_at: datetime
    options: RenderOptions
    warnings: list[str]
    logs: str
    logs_truncated: bool
    error: str | None
    files: list[Artifact]
    status_url: str
