# app/api/routes/receipts.py
"""
レシート確認・修正・承認 API ルーター

提供エンドポイント:
- GET    /api/v1/receipts                     未承認/承認済みレシートの一覧
- GET    /api/v1/receipts/{receipt_id}        詳細 (ヘッダー + 品目 + OCRテキスト)
- GET    /api/v1/receipts/{receipt_id}/image   原本画像 (L1 CASから認証付きで取得)
- PATCH  /api/v1/receipts/{receipt_id}        内容の修正 (保存と承認を同一トランザクションで実行可能)
- POST   /api/v1/receipts/{receipt_id}/approve    承認
- POST   /api/v1/receipts/{receipt_id}/unapprove  承認取り消し

設計メモ:
- 「未承認」は approved_at IS NULL で判定する (needs_review とは独立)。
  パーサーが needs_review=False を付けても人間が承認するまで未承認。
- 承認時に needs_review / review_reasons は書き換えない (抽出時の警告を残す)。
- 承認済みレシートを編集すると承認状態は自動的に無効化 (approved_at を NULL に戻す)。
  approve=True を同時に指定した場合は変更を反映したうえで再承認する。
- アクセス権は L1FileUpload の所有権と ResourceShare (user/group 共有) から判定する。
  Owner/Admin/Write が編集・承認可、Read は閲覧のみ。
"""

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db_all_models  # noqa: F401  # リレーション解決のためモデルを一括登録
from app.api.routes.auth import get_current_user_id
from app.core.config import settings
from app.infrastructure.db.models.auth import GroupMember, ResourceShare
from app.infrastructure.db.session import get_db_session
from app.infrastructure.storage import LocalStorageAdapter
from app.layers.l1_raw.models import L1File, L1FileUpload
from app.layers.l2_extracted.models import L2Artifact
from app.layers.l3_structured.addons.receipt.models import ReceiptItem, ReceiptTotal

logger = logging.getLogger("datacore.receipts")

router = APIRouter(prefix="/api/v1", tags=["receipts"])

# ---------------------------------------------------------------------------
# 権限ヘルパー
# ---------------------------------------------------------------------------

_WRITE_LEVELS = ("owner", "admin", "write")
_READ_LEVELS_LOWER = ("read", "write", "admin")


def _permission_rank(level: str) -> int:
    return {"owner": 4, "admin": 3, "write": 2, "read": 1}.get(level.lower(), 0)


def _accessible_file_hashes_subquery(user_id: uuid.UUID):
    """ユーザーが閲覧可能な file_hash の集合 (所有 + Read以上の共有)。

    共有は permission_level が Read/Write/Admin のいずれかの場合のみ有効扱いとする
    (不正な値の共有エントリでは閲覧させない。
    _resolve_access のランク判定と一貫させるため小文字比較)。
    """
    owned = select(L1FileUpload.file_hash).where(L1FileUpload.user_id == user_id)

    user_shared = (
        select(L1FileUpload.file_hash)
        .join(ResourceShare, ResourceShare.file_upload_id == L1FileUpload.id)
        .where(
            ResourceShare.grantee_type == "user",
            ResourceShare.grantee_id == user_id,
            func.lower(ResourceShare.permission_level).in_(_READ_LEVELS_LOWER),
        )
    )

    group_shared = (
        select(L1FileUpload.file_hash)
        .join(ResourceShare, ResourceShare.file_upload_id == L1FileUpload.id)
        .join(GroupMember, GroupMember.group_id == ResourceShare.grantee_id)
        .where(
            ResourceShare.grantee_type == "group",
            GroupMember.user_id == user_id,
            func.lower(ResourceShare.permission_level).in_(_READ_LEVELS_LOWER),
        )
    )

    return owned.union(user_shared, group_shared)


async def _resolve_access(
    session: AsyncSession, user_id: uuid.UUID, file_hash: str
) -> Optional[str]:
    """対象ファイルに対するユーザーの権限レベルを返す (owner/admin/write/read/None)。"""
    owned = (
        await session.execute(
            select(L1FileUpload.id).where(
                L1FileUpload.user_id == user_id,
                L1FileUpload.file_hash == file_hash,
            )
        )
    ).first()
    if owned is not None:
        return "owner"

    shares = (
        await session.execute(
            select(ResourceShare.permission_level)
            .join(L1FileUpload, L1FileUpload.id == ResourceShare.file_upload_id)
            .where(
                L1FileUpload.file_hash == file_hash,
                func.lower(ResourceShare.permission_level).in_(_READ_LEVELS_LOWER),
                or_(
                    (ResourceShare.grantee_type == "user")
                    & (ResourceShare.grantee_id == user_id),
                    (ResourceShare.grantee_type == "group")
                    & ResourceShare.grantee_id.in_(
                        select(GroupMember.group_id).where(
                            GroupMember.user_id == user_id
                        )
                    ),
                ),
            )
        )
    ).scalars().all()

    best = max((_permission_rank(level) for level in shares), default=0)
    if best >= 3:
        return "admin"
    if best == 2:
        return "write"
    if best == 1:
        return "read"
    return None


async def _original_filenames_for_user(
    session: AsyncSession, user_id: uuid.UUID, file_hashes: set[str]
) -> dict[str, str]:
    """呼び出し元が所有またはRead以上で共有されたアップロードから元ファイル名を返す。

    ファイルはグローバル重複排除されるため同一ハッシュに他ユーザーのアップロードが
    存在し得るが、それらのファイル名は参照しない (プライバシー保護)。
    """
    filenames: dict[str, str] = {}
    if not file_hashes:
        return filenames

    owned = (
        await session.execute(
            select(L1FileUpload.file_hash, L1FileUpload.original_filename)
            .where(
                L1FileUpload.user_id == user_id,
                L1FileUpload.file_hash.in_(file_hashes),
            )
            .order_by(L1FileUpload.created_at.asc())
        )
    ).all()
    for file_hash, name in owned:
        filenames.setdefault(file_hash, name)

    shared = (
        await session.execute(
            select(L1FileUpload.file_hash, L1FileUpload.original_filename)
            .join(ResourceShare, ResourceShare.file_upload_id == L1FileUpload.id)
            .where(
                L1FileUpload.file_hash.in_(file_hashes),
                func.lower(ResourceShare.permission_level).in_(_READ_LEVELS_LOWER),
                or_(
                    (ResourceShare.grantee_type == "user")
                    & (ResourceShare.grantee_id == user_id),
                    (ResourceShare.grantee_type == "group")
                    & ResourceShare.grantee_id.in_(
                        select(GroupMember.group_id).where(
                            GroupMember.user_id == user_id
                        )
                    ),
                ),
            )
            .order_by(L1FileUpload.created_at.asc())
        )
    ).all()
    for file_hash, name in shared:
        filenames.setdefault(file_hash, name)

    return filenames


async def _get_receipt_or_404(
    session: AsyncSession, receipt_id: uuid.UUID
) -> ReceiptTotal:
    receipt = await session.get(ReceiptTotal, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="指定されたレシートが見つかりません。")
    return receipt


async def _require_receipt_access(
    session: AsyncSession,
    receipt_id: uuid.UUID,
    user_id: str,
    *,
    write: bool = False,
) -> tuple[ReceiptTotal, str, uuid.UUID]:
    """レシートを取得し、アクセス権を検証する。write=True の場合は編集権限が必要。"""
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="トークン内のユーザーIDが不正です。")

    receipt = await _get_receipt_or_404(session, receipt_id)
    level = await _resolve_access(session, user_uuid, receipt.file_hash)

    if level is None:
        # 存在を悟られないよう 404 で応答
        raise HTTPException(status_code=404, detail="指定されたレシートが見つかりません。")
    if write and level not in _WRITE_LEVELS:
        raise HTTPException(status_code=403, detail="このレシートを編集する権限がありません。")

    return receipt, level or "read", user_uuid


# ---------------------------------------------------------------------------
# Pydantic スキーマ
# ---------------------------------------------------------------------------


def _fmt_amount(value: Optional[Decimal]) -> Optional[str]:
    """金額を精度を落とさない文字列へ変換 (JSON 数値化による誤差を防ぐ)。"""
    if value is None:
        return None
    return str(value)


class ReceiptSummary(BaseModel):
    id: str
    file_hash: str
    original_filename: Optional[str] = None
    store_name: Optional[str] = None
    transaction_date: Optional[date] = None
    transaction_at: Optional[datetime] = None
    currency: Optional[str] = None
    subtotal_amount: Optional[str] = None
    discount_amount: Optional[str] = None
    tax_amount: Optional[str] = None
    total_amount: Optional[str] = None
    payment_method: Optional[str] = None
    needs_review: bool
    review_reasons: list[str]
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    item_count: int
    created_at: Optional[datetime] = None


class ReceiptListResponse(BaseModel):
    total: int
    pending_total: int
    items: list[ReceiptSummary]


class ReceiptItemOut(BaseModel):
    line_number: int
    item_name: str
    quantity: Optional[str] = None
    unit_price: Optional[str] = None
    line_amount: Optional[str] = None
    tax_rate: Optional[str] = None
    raw_text: Optional[str] = None


class ReceiptDetail(ReceiptSummary):
    items: list[ReceiptItemOut]
    ocr_text: Optional[str] = None
    mime_type: Optional[str] = None
    permission: str  # owner / admin / write / read


class ReceiptItemIn(BaseModel):
    item_name: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    raw_text: Optional[str] = None


class ReceiptUpdate(BaseModel):
    """PATCH リクエストボディ。

    - フィールド省略時: 変更しない
    - 明示的な null: NULLクリア (NULL許可カラム)
    - items 省略時: 品目は変更しない / items: [] で全品目削除
    - approve: true なら変更を保存して承認 / false なら承認を取り消す
    """

    store_name: Optional[str] = None
    transaction_date: Optional[date] = None
    transaction_at: Optional[datetime] = None
    currency: Optional[str] = None
    subtotal_amount: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    payment_method: Optional[str] = None
    items: Optional[list[ReceiptItemIn]] = None
    approve: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 一覧
# ---------------------------------------------------------------------------


@router.get("/receipts", response_model=ReceiptListResponse)
async def list_receipts(
    status: str = Query(
        "pending", pattern="^(pending|approved|all)$",
        description="pending=未承認, approved=承認済み, all=すべて",
    ),
    store: Optional[str] = Query(None, max_length=255, description="店舗名の部分一致検索"),
    date_from: Optional[date] = Query(None, description="取引日 (この日以降)"),
    date_to: Optional[date] = Query(None, description="取引日 (この日以前)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> ReceiptListResponse:
    """アクセス権のあるレシートを一覧表示する。未承認 = approved_at IS NULL。"""
    user_uuid = uuid.UUID(user_id)

    base = select(ReceiptTotal).where(
        ReceiptTotal.file_hash.in_(_accessible_file_hashes_subquery(user_uuid))
    )

    if status == "pending":
        base = base.where(ReceiptTotal.approved_at.is_(None))
    elif status == "approved":
        base = base.where(ReceiptTotal.approved_at.is_not(None))
    if store:
        base = base.where(ReceiptTotal.store_name.ilike(f"%{store}%"))
    if date_from:
        base = base.where(ReceiptTotal.transaction_date >= date_from)
    if date_to:
        base = base.where(ReceiptTotal.transaction_date <= date_to)

    total = (
        await session.execute(
            select(func.count()).select_from(base.subquery())
        )
    ).scalar_one()

    rows = (
        (
            await session.execute(
                base.order_by(ReceiptTotal.created_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )

    # 未承認件数 (フィルタ状態に関わらず常に返す)
    pending_stmt = (
        select(func.count())
        .select_from(ReceiptTotal)
        .where(
            ReceiptTotal.file_hash.in_(_accessible_file_hashes_subquery(user_uuid)),
            ReceiptTotal.approved_at.is_(None),
        )
    )
    pending_total = (await session.execute(pending_stmt)).scalar_one()

    receipt_ids = [r.id for r in rows]
    file_hashes = {r.file_hash for r in rows}

    item_counts: dict[uuid.UUID, int] = {}
    original_names: dict[str, str] = {}
    approved_by_names: dict[uuid.UUID, str] = {}

    if receipt_ids:
        counts = (
            await session.execute(
                select(ReceiptItem.receipt_id, func.count())
                .where(ReceiptItem.receipt_id.in_(receipt_ids))
                .group_by(ReceiptItem.receipt_id)
            )
        ).all()
        item_counts = {rid: count for rid, count in counts}

    if file_hashes:
        # 呼び出し元が所有またはRead以上で共有されたアップロードからのみ採用
        original_names = await _original_filenames_for_user(
            session, user_uuid, file_hashes
        )

    from app.infrastructure.db.models.users import User

    approver_ids = {r.approved_by for r in rows if r.approved_by is not None}
    if approver_ids:
        approvers = (
            await session.execute(
                select(User.id, User.username).where(User.id.in_(approver_ids))
            )
        ).all()
        approved_by_names = {uid: name for uid, name in approvers}

    items = [
        ReceiptSummary(
            id=str(r.id),
            file_hash=r.file_hash,
            original_filename=original_names.get(r.file_hash),
            store_name=r.store_name,
            transaction_date=r.transaction_date,
            transaction_at=r.transaction_at,
            currency=r.currency,
            subtotal_amount=_fmt_amount(r.subtotal_amount),
            discount_amount=_fmt_amount(r.discount_amount),
            tax_amount=_fmt_amount(r.tax_amount),
            total_amount=_fmt_amount(r.total_amount),
            payment_method=r.payment_method,
            needs_review=r.needs_review,
            review_reasons=list(r.review_reasons or []),
            approved_at=r.approved_at,
            approved_by=(
                str(r.approved_by) if r.approved_by is not None else None
            ),
            item_count=item_counts.get(r.id, 0),
            created_at=r.created_at,
        )
        for r in rows
    ]
    # 承認者名は別途参照用に付与 (UI表示用)
    for summary, r in zip(items, rows):
        if r.approved_by is not None:
            summary.approved_by = approved_by_names.get(
                r.approved_by, str(r.approved_by)
            )

    return ReceiptListResponse(
        total=total, pending_total=pending_total, items=items
    )


# ---------------------------------------------------------------------------
# 詳細
# ---------------------------------------------------------------------------


@router.get("/receipts/{receipt_id}", response_model=ReceiptDetail)
async def get_receipt_detail(
    receipt_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> ReceiptDetail:
    receipt, level, user_uuid = await _require_receipt_access(
        session, receipt_id, user_id, write=False
    )

    ocr_text: Optional[str] = None
    if receipt.source_artifact_id is not None:
        source = await session.get(L2Artifact, receipt.source_artifact_id)
        if source is not None:
            ocr_text = source.content_text

    l1_file = await session.get(L1File, receipt.file_hash)
    mime_type = l1_file.mime_type if l1_file is not None else None

    item_rows = (
        (
            await session.execute(
                select(ReceiptItem)
                .where(ReceiptItem.receipt_id == receipt.id)
                .order_by(ReceiptItem.line_number.asc())
            )
        )
        .scalars()
        .all()
    )

    name_map = await _original_filenames_for_user(
        session, user_uuid, {receipt.file_hash}
    )
    original_filename = name_map.get(receipt.file_hash)

    return ReceiptDetail(
        id=str(receipt.id),
        file_hash=receipt.file_hash,
        original_filename=original_filename,
        store_name=receipt.store_name,
        transaction_date=receipt.transaction_date,
        transaction_at=receipt.transaction_at,
        currency=receipt.currency,
        subtotal_amount=_fmt_amount(receipt.subtotal_amount),
        discount_amount=_fmt_amount(receipt.discount_amount),
        tax_amount=_fmt_amount(receipt.tax_amount),
        total_amount=_fmt_amount(receipt.total_amount),
        payment_method=receipt.payment_method,
        needs_review=receipt.needs_review,
        review_reasons=list(receipt.review_reasons or []),
        approved_at=receipt.approved_at,
        approved_by=str(receipt.approved_by) if receipt.approved_by else None,
        item_count=len(item_rows),
        created_at=receipt.created_at,
        items=[
            ReceiptItemOut(
                line_number=item.line_number,
                item_name=item.item_name,
                quantity=_fmt_amount(item.quantity),
                unit_price=_fmt_amount(item.unit_price),
                line_amount=_fmt_amount(item.line_amount),
                tax_rate=_fmt_amount(item.tax_rate),
                raw_text=item.raw_text,
            )
            for item in item_rows
        ],
        ocr_text=ocr_text,
        mime_type=mime_type,
        permission=level,
    )


# ---------------------------------------------------------------------------
# 原本画像
# ---------------------------------------------------------------------------


@router.get("/receipts/{receipt_id}/image")
async def get_receipt_image(
    receipt_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """L1 CAS から原本ファイルを取得して返す (JWTはAuthorizationヘッダー必須)。

    WebUIのサーバー側 (Reflexバックエンド) からhttpxで呼び、
    data URL化してブラウザへ配ることを想定している。
    """
    receipt, _, _ = await _require_receipt_access(
        session, receipt_id, user_id, write=False
    )

    l1_file = await session.get(L1File, receipt.file_hash)
    if l1_file is None or not l1_file.storage_path:
        raise HTTPException(status_code=404, detail="原本ファイルが見つかりません。")

    adapter = LocalStorageAdapter()
    content = await adapter.load(receipt.file_hash)
    if content is None:
        raise HTTPException(status_code=404, detail="CAS上に原本ファイルが存在しません。")

    return Response(content=content, media_type=l1_file.mime_type)


# ---------------------------------------------------------------------------
# 修正 (保存 / 保存して承認)
# ---------------------------------------------------------------------------


@router.patch("/receipts/{receipt_id}", response_model=ReceiptDetail)
async def update_receipt(
    receipt_id: uuid.UUID,
    payload: ReceiptUpdate,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> ReceiptDetail:
    """レシートの内容を修正する。

    - header フィールド: 省略=変更しない / null=クリア
    - items: 省略=変更しない / 指定時=全行差し替え (line_numberを1から振り直し)
    - approve=True: 変更保存と承認を同一トランザクションで実行
    - approve 未指定かつ変更あり & 承認済み: 承認を自動で無効化 (要再承認)
    """
    receipt, level, user_uuid = await _require_receipt_access(
        session, receipt_id, user_id, write=True
    )

    data: dict[str, Any] = payload.model_dump(exclude_unset=True)

    header_fields = (
        "store_name",
        "transaction_date",
        "transaction_at",
        "currency",
        "subtotal_amount",
        "discount_amount",
        "tax_amount",
        "total_amount",
        "payment_method",
    )

    changed = False

    for field in header_fields:
        if field in data:
            setattr(receipt, field, data[field])
            changed = True

    if "items" in data:
        # 品目は全行差し替え: 削除→flush→再挿入 (UniqueConstraint回避のため必ずflushを挟む)
        await session.execute(
            delete(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id)
        )
        await session.flush()

        new_items = payload.items or []
        for line_number, item in enumerate(new_items, start=1):
            session.add(
                ReceiptItem(
                    receipt_id=receipt.id,
                    line_number=line_number,
                    item_name=item.item_name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_amount=item.line_amount,
                    tax_rate=item.tax_rate,
                    raw_text=item.raw_text,
                )
            )
        changed = True

    # ---- 承認状態の遷移 ----
    if payload.approve is True:
        receipt.approved_at = datetime.now(settings.tz_info)
        receipt.approved_by = user_uuid
    elif payload.approve is False:
        receipt.approved_at = None
        receipt.approved_by = None
    elif changed and receipt.approved_at is not None:
        # 承認済みデータへの追加編集は承認を無効化する
        receipt.approved_at = None
        receipt.approved_by = None

    await session.flush()

    logger.info(
        "[RECEIPT UPDATE] receipt=%s user=%s changed=%s approve=%s",
        receipt_id, user_id, changed, payload.approve,
    )

    # 以降は詳細取得と同じ組み立て (アクセス検証済みなので権限チェックは省略)
    return await _build_detail(session, receipt, level, user_uuid)


async def _build_detail(
    session: AsyncSession, receipt: ReceiptTotal, level: str, user_uuid: uuid.UUID
) -> ReceiptDetail:
    """保存後のレスポンス構築 (get_receipt_detail と同内容)。"""
    ocr_text: Optional[str] = None
    if receipt.source_artifact_id is not None:
        source = await session.get(L2Artifact, receipt.source_artifact_id)
        if source is not None:
            ocr_text = source.content_text

    l1_file = await session.get(L1File, receipt.file_hash)
    mime_type = l1_file.mime_type if l1_file is not None else None

    item_rows = (
        (
            await session.execute(
                select(ReceiptItem)
                .where(ReceiptItem.receipt_id == receipt.id)
                .order_by(ReceiptItem.line_number.asc())
            )
        )
        .scalars()
        .all()
    )

    name_map = await _original_filenames_for_user(
        session, user_uuid, {receipt.file_hash}
    )

    return ReceiptDetail(
        id=str(receipt.id),
        file_hash=receipt.file_hash,
        original_filename=uploads[0] if uploads else None,
        store_name=receipt.store_name,
        transaction_date=receipt.transaction_date,
        transaction_at=receipt.transaction_at,
        currency=receipt.currency,
        subtotal_amount=_fmt_amount(receipt.subtotal_amount),
        discount_amount=_fmt_amount(receipt.discount_amount),
        tax_amount=_fmt_amount(receipt.tax_amount),
        total_amount=_fmt_amount(receipt.total_amount),
        payment_method=receipt.payment_method,
        needs_review=receipt.needs_review,
        review_reasons=list(receipt.review_reasons or []),
        approved_at=receipt.approved_at,
        approved_by=str(receipt.approved_by) if receipt.approved_by else None,
        item_count=len(item_rows),
        created_at=receipt.created_at,
        items=[
            ReceiptItemOut(
                line_number=item.line_number,
                item_name=item.item_name,
                quantity=_fmt_amount(item.quantity),
                unit_price=_fmt_amount(item.unit_price),
                line_amount=_fmt_amount(item.line_amount),
                tax_rate=_fmt_amount(item.tax_rate),
                raw_text=item.raw_text,
            )
            for item in item_rows
        ],
        ocr_text=ocr_text,
        mime_type=mime_type,
        permission=level,
    )


# ---------------------------------------------------------------------------
# 承認 / 承認取り消し
# ---------------------------------------------------------------------------


@router.post("/receipts/{receipt_id}/approve", response_model=ReceiptDetail)
async def approve_receipt(
    receipt_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> ReceiptDetail:
    """レシートを承認する。needs_review / review_reasons は変更しない。"""
    receipt, level, user_uuid = await _require_receipt_access(
        session, receipt_id, user_id, write=True
    )
    receipt.approved_at = datetime.now(settings.tz_info)
    receipt.approved_by = user_uuid
    await session.flush()

    logger.info("[RECEIPT APPROVE] receipt=%s user=%s", receipt_id, user_id)
    return await _build_detail(session, receipt, level, user_uuid)


@router.post("/receipts/{receipt_id}/unapprove", response_model=ReceiptDetail)
async def unapprove_receipt(
    receipt_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> ReceiptDetail:
    """承認を取り消して未承認に戻す。"""
    receipt, level, _ = await _require_receipt_access(
        session, receipt_id, user_id, write=True
    )
    receipt.approved_at = None
    receipt.approved_by = None
    await session.flush()

    logger.info("[RECEIPT UNAPPROVE] receipt=%s user=%s", receipt_id, user_id)
    return await _build_detail(session, receipt, level, user_uuid)
