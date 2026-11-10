from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LayoutGeometry(BaseModel):
    model_config = ConfigDict(extra="allow")

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    center_x: float
    center_y: float
    width: float
    height: float


class LayoutBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_index: int
    text: str = ""
    geometry: LayoutGeometry


class LayoutLine(BaseModel):
    line_index: int
    text: str
    center_x: float | None = None
    center_y: float | None = None
    line_center: float | None = None
    bbox: dict[str, float] = Field(default_factory=dict)
    blocks: list[LayoutBlock] = Field(default_factory=list)


class LayoutDirectionInference(BaseModel):
    model_config = ConfigDict(extra="allow")

    text_direction: Literal["horizontal", "vertical"]
    confidence: float | None = None


class YomitokuLayoutResult(BaseModel):
    file_hash: str
    artifact_id: str
    run_id: str | None = None
    tool_id: str | None = None
    status: Literal["completed", "already_exists", "skipped"]
    reason: str | None = None
    layout_method: str | None = None
    text_direction: str | None = None
    line_count: int = 0
    word_count: int = 0
    lines: list[LayoutLine] = Field(default_factory=list)