from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import get_current_user_id
from app.infrastructure.db.session import get_db_session
from app.layers.l2_extracted.search.service import (
    list_searchable_tools,
    search_artifacts,
    search_media_info,
)


router = APIRouter(
    prefix="/api/v1/search",
    tags=["search"],
)


# ============================================================
# Response Schemas
# ============================================================

class ToolOption(BaseModel):
    tool_id: str
    tool_name: str
    tool_type: str
    model_name: str | None = None
    output_dim: int | None = None


class ToolListResponse(BaseModel):
    tools: list[ToolOption]


class SearchResult(BaseModel):
    mode: str
    tool: dict[str, Any]
    results: list[dict[str, Any]]


# ============================================================
# GET /api/v1/search/tools
# ============================================================

@router.get(
    "/tools",
    response_model=ToolListResponse,
)
async def get_tools(
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    ログインユーザーが利用できる検索ツール一覧を取得する。
    """

    tools = await list_searchable_tools(
        session,
        user_id,
    )

    return {
        "tools": tools,
    }


# ============================================================
# GET /api/v1/search/artifacts
# ============================================================

@router.get(
    "/artifacts",
    response_model=SearchResult,
)
async def search_artifact_endpoint(
    tool_id: UUID = Query(...),
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    指定されたL2Toolを使用してL2Artifactを検索する。
    """

    try:
        return await search_artifacts(
            session,
            user_id,
            tool_id,
            q,
            limit,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ============================================================
# GET /api/v1/search/mediainfo
# ============================================================

@router.get(
    "/mediainfo",
    response_model=SearchResult,
)
async def search_mediainfo_endpoint(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    L2MediaInfoを検索する。
    """

    return await search_media_info(
        session,
        user_id,
        q,
        limit,
    )
