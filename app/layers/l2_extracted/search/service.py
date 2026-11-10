from typing import Any
from uuid import UUID

from sqlalchemy import (
    String,
    and_,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.l2_tools import L2Tool
from app.layers.l1_raw.models import L1File, L1FileUpload
from app.layers.l2_extracted.models import L2Artifact, L2MediaInfo


# ============================================================
# 共通処理
# ============================================================

def _normalize_user_id(user_id: UUID | str) -> UUID:
    """user_id を UUID に統一する。"""
    if isinstance(user_id, UUID):
        return user_id

    try:
        return UUID(str(user_id))
    except (ValueError, TypeError, AttributeError) as e:
        raise ValueError("不正な user_id です") from e


def _owned_artifact_exists(
    user_id: UUID,
    tool_id: Any,
    *,
    require_text: bool = False,
    require_embedding: bool = False,
):
    """
    指定ユーザーがアップロードしたファイルに、
    指定Toolの検索対象Artifactが存在するか確認する。

    JOINによる検索結果の重複を避けるため EXISTS を使用する。
    """
    conditions = [
        L2Artifact.tool_id == tool_id,
        L1FileUpload.user_id == user_id,
        L1FileUpload.file_hash == L2Artifact.file_hash,
    ]

    if require_text:
        conditions.append(L2Artifact.content_text.is_not(None))

    if require_embedding:
        conditions.append(L2Artifact.embedding.is_not(None))

    return exists(
        select(1)
        .select_from(L2Artifact)
        .join(
            L1FileUpload,
            L1FileUpload.file_hash == L2Artifact.file_hash,
        )
        .where(*conditions)
    )


def _text_embedding_plugins():
    """テキストEmbeddingプラグイン一覧を取得する。"""
    from app.layers.l2_extracted.embedding_text.service import (
        TEXT_EMBEDDING_PLUGINS,
    )

    return TEXT_EMBEDDING_PLUGINS


# ============================================================
# 検索可能な L2Tool 一覧
# ============================================================

async def list_searchable_tools(
    session: AsyncSession,
    user_id: UUID | str,
) -> list[dict[str, Any]]:
    """
    ログインユーザーが検索できる L2Tool の一覧を返す。

    対象:
      - ocr / text / parser:
          content_text が存在するArtifactを持つTool
      - embedding:
          テキストEmbeddingプラグインが存在し、
          embedding が存在するArtifactを持つTool
    """
    user_uuid = _normalize_user_id(user_id)

    text_tool_exists = _owned_artifact_exists(
        user_uuid,
        L2Tool.id,
        require_text=True,
    )

    embedding_tool_exists = _owned_artifact_exists(
        user_uuid,
        L2Tool.id,
        require_embedding=True,
    )

    plugins = _text_embedding_plugins()

    conditions = [
        and_(
            L2Tool.tool_type.in_(["ocr", "text", "parser"]),
            text_tool_exists,
        )
    ]

    if plugins:
        conditions.append(
            and_(
                L2Tool.tool_type == "embedding",
                L2Tool.name.in_(list(plugins.keys())),
                embedding_tool_exists,
            )
        )

    stmt = (
        select(
            L2Tool.id,
            L2Tool.name,
            L2Tool.tool_type,
            L2Tool.model_name,
            L2Tool.output_dim,
        )
        .where(or_(*conditions))
        .order_by(L2Tool.name)
    )

    result = await session.execute(stmt)

    return [
        {
            "tool_id": str(row.id),
            "tool_name": row.name,
            "tool_type": row.tool_type,
            "model_name": row.model_name,
            "output_dim": row.output_dim,
        }
        for row in result.all()
    ]


# ============================================================
# L2Artifact 検索
# ============================================================

async def search_artifacts(
    session: AsyncSession,
    user_id: UUID | str,
    tool_id: UUID,
    query: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    L2Toolを指定してArtifactを検索する。

    OCR / text / parser:
        content_text の部分一致検索

    embedding:
        テキストEmbeddingによるコサイン類似度検索
    """
    user_uuid = _normalize_user_id(user_id)

    query = query.strip()
    if not query:
        raise ValueError("検索文字列が空です")

    # --------------------------------------------------------
    # Tool取得
    # --------------------------------------------------------

    tool_stmt = select(L2Tool).where(L2Tool.id == tool_id)
    tool_result = await session.execute(tool_stmt)
    tool = tool_result.scalar_one_or_none()

    if tool is None:
        raise ValueError("指定された L2Tool が存在しません")

    # --------------------------------------------------------
    # 共通SELECT項目
    # --------------------------------------------------------

    base_columns = (
        L2Artifact.id.label("artifact_id"),
        L2Artifact.file_hash.label("filehash"),
        L2Artifact.artifact_type,
        L2Artifact.content_text,
        L2Artifact.page_number,
        L2Artifact.metadata_json,
        L2Artifact.created_at,
        L1File.mime_type.label("mimetype"),
        L2Tool.name.label("tool_name"),
    )

    ownership_condition = exists(
        select(1)
        .select_from(L1FileUpload)
        .where(
            L1FileUpload.file_hash == L2Artifact.file_hash,
            L1FileUpload.user_id == user_uuid,
        )
    )

    # --------------------------------------------------------
    # OCR / text / parser
    # --------------------------------------------------------

    if tool.tool_type in {"ocr", "text", "parser"}:
        pattern = f"%{query}%"

        score = literal(0.0).label("score")

        stmt = (
            select(
                *base_columns,
                score,
            )
            .join(
                L1File,
                L1File.file_hash == L2Artifact.file_hash,
            )
            .join(
                L2Tool,
                L2Tool.id == L2Artifact.tool_id,
            )
            .where(
                L2Artifact.tool_id == tool.id,
                L2Artifact.content_text.ilike(pattern),
                ownership_condition,
            )
            .order_by(L2Artifact.created_at.desc())
            .limit(limit)
        )

        rows = (
            await session.execute(stmt)
        ).mappings().all()

        return {
            "mode": "text",
            "tool": {
                "id": str(tool.id),
                "name": tool.name,
            },
            "results": [
                _artifact_row(row)
                for row in rows
            ],
        }

    # --------------------------------------------------------
    # Embedding
    # --------------------------------------------------------

    if tool.tool_type == "embedding":
        plugins = _text_embedding_plugins()

        if tool.name not in plugins:
            raise ValueError(
                f"ツール '{tool.name}' は"
                "テキストクエリのベクトル化に対応していません"
            )

        vector = await _embed_query(tool.name, query)

        if tool.output_dim and len(vector) != tool.output_dim:
            raise ValueError(
                "Embedding dimension mismatch: "
                f"expected={tool.output_dim}, actual={len(vector)}"
            )

        distance = L2Artifact.embedding.cosine_distance(
            vector
        )

        score = (1.0 - distance).label("score")

        stmt = (
            select(
                *base_columns,
                score,
            )
            .join(
                L1File,
                L1File.file_hash == L2Artifact.file_hash,
            )
            .join(
                L2Tool,
                L2Tool.id == L2Artifact.tool_id,
            )
            .where(
                L2Artifact.tool_id == tool.id,
                L2Artifact.embedding.is_not(None),
                ownership_condition,
            )
            .order_by(distance.asc())
            .limit(limit)
        )

        rows = (
            await session.execute(stmt)
        ).mappings().all()

        return {
            "mode": "embedding",
            "tool": {
                "id": str(tool.id),
                "name": tool.name,
            },
            "results": [
                _artifact_row(row)
                for row in rows
            ],
        }

    raise ValueError(
        f"ツール '{tool.name}' "
        f"(tool_type={tool.tool_type}) は検索に対応していません"
    )


# ============================================================
# MediaInfo 検索
# ============================================================

async def search_media_info(
    session: AsyncSession,
    user_id: UUID | str,
    query: str,
    limit: int = 20,
) -> dict[str, Any]:
    """
    L2MediaInfo を検索する。

    検索対象:
      - author_or_device
      - raw_metadata

    ログインユーザーがアップロードしたファイルに限定する。
    """
    user_uuid = _normalize_user_id(user_id)

    query = query.strip()
    if not query:
        raise ValueError("検索文字列が空です")

    pattern = f"%{query}%"

    ownership_condition = exists(
        select(1)
        .select_from(L1FileUpload)
        .where(
            L1FileUpload.file_hash == L2MediaInfo.file_hash,
            L1FileUpload.user_id == user_uuid,
        )
    )

    stmt = (
        select(
            L2MediaInfo.file_hash,
            L2MediaInfo.author_or_device,
            L2MediaInfo.content_created_at,
            L2MediaInfo.width,
            L2MediaInfo.height,
            L2MediaInfo.latitude,
            L2MediaInfo.longitude,
            L2MediaInfo.raw_metadata,
            L2MediaInfo.created_at,
            L1File.mime_type,
        )
        .join(
            L1File,
            L1File.file_hash == L2MediaInfo.file_hash,
        )
        .where(
            or_(
                func.coalesce(
                    L2MediaInfo.author_or_device,
                    "",
                ).ilike(pattern),
                cast(
                    L2MediaInfo.raw_metadata,
                    String,
                ).ilike(pattern),
            ),
            ownership_condition,
        )
        .order_by(L2MediaInfo.created_at.desc())
        .limit(limit)
    )

    rows = (
        await session.execute(stmt)
    ).all()

    return {
        "mode": "mediainfo",
        "tool": {
            "id": None,
            "name": "l2mediainfo",
        },
        "results": [
            {
                "filehash": row.file_hash,
                "mimetype": row.mime_type,
                "author_or_device": row.author_or_device,
                "content_created_at": (
                    row.content_created_at.isoformat()
                    if row.content_created_at
                    else None
                ),
                "width": row.width,
                "height": row.height,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "raw_metadata": row.raw_metadata,
                "created_at": (
                    row.created_at.isoformat()
                    if row.created_at
                    else None
                ),
            }
            for row in rows
        ],
    }


# ============================================================
# Embedding Query
# ============================================================

async def _embed_query(
    tool_name: str,
    query: str,
) -> list[float]:
    """
    登録済みテキストEmbeddingプラグインで検索文字列をベクトル化する。
    """
    plugins = _text_embedding_plugins()

    plugin = plugins.get(tool_name)

    if plugin is None:
        raise ValueError(
            f"ツール '{tool_name}' は"
            "クエリのベクトル化に対応していません"
        )

    result = await plugin.embed_text(query)

    return result.vector


# ============================================================
# 検索結果変換
# ============================================================

def _artifact_row(row) -> dict[str, Any]:
    """
    SQLAlchemy RowMapping をAPIレスポンス用dictに変換する。
    """
    return {
        "artifact_id": str(row["artifact_id"]),
        "filehash": row["filehash"],
        "artifact_type": row["artifact_type"],
        "tool_name": row["tool_name"],
        "mimetype": row["mimetype"],
        "content_text": row["content_text"],
        "page_number": row["page_number"],
        "metadata_json": row["metadata_json"],
        "created_at": (
            row["created_at"].isoformat()
            if row["created_at"]
            else None
        ),
        "score": (
            float(row["score"])
            if row["score"] is not None
            else None
        ),
    }
