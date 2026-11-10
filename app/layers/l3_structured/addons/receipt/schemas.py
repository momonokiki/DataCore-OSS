from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

@field_validator("currency", mode="before")
@classmethod
def normalize_currency(cls, value):
    if value is None or value == "":
        return "JPY"
    if value in ("¥", "￥", "円"):
        return "JPY"
    return value

class ReceiptHeaderData(BaseModel):
    """Step 1: レシート判定と合計情報"""

    model_config = ConfigDict(extra="forbid")

    is_receipt: bool = Field(
        ...,
        description="レシートまたは領収書ならtrue",
    )
    store_name: str | None = Field(
        default=None,
        max_length=255,
        description="店舗名",
    )
    transaction_date: date | None = Field(
        default=None,
        description="取引日。YYYY-MM-DD",
    )
    transaction_at: datetime | None = Field(
        default=None,
        description="取引日時。タイムゾーンが確定しない場合はnull",
    )
    currency: str |None= Field(
        default="JPY",
        pattern=r"^[A-Z]{3}$",
        description="通貨コード",
    )
    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value):
        if value is None or value == "":
            return "JPY"
        if value in ("¥", "￥", "円"):
            return "JPY"
        return value
    subtotal_amount: Decimal | None = Field(
        default=None,
        max_digits=14,
        decimal_places=2,
        description="小計",
    )
    discount_amount: Decimal | None = Field(
        default=None,
        max_digits=14,
        decimal_places=2,
        description="全体値引き額",
    )
    tax_amount: Decimal | None = Field(
        default=None,
        max_digits=14,
        decimal_places=2,
        description="消費税額",
    )
    total_amount: Decimal | None = Field(
        default=None,
        max_digits=14,
        decimal_places=2,
        description="合計または支払総額",
    )
    payment_method: str | None = Field(
        default=None,
        max_length=100,
        description="支払方法",
    )

    @field_validator("transaction_at", mode="before")
    @classmethod
    def parse_and_normalize_transaction_at(cls, value: Any) -> datetime | None:
        if value is None or value == "":
            return None

        # 文字列として渡ってきた場合のパースと補正
        if isinstance(value, str):
            value = value.strip()
            
            # 時刻のみ（例: "21:05:11" や "18:54"）の場合は日付が不明なため安全に None にする
            if re.match(r"^\d{2}:\d{2}(?::\d{2})?$", value):
                return None

            try:
                # ISO形式や "YYYY-MM-DD HH:MM:SS" などをパース
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        elif isinstance(value, datetime):
            dt = value
        else:
            return None

        # タイムゾーンがない場合はデフォルトで JST (+09:00) を付与する
        if dt.tzinfo is None or dt.utcoffset() is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Tokyo"))

        return dt

    def review_reasons(self) -> list[str]:
        reasons: list[str] = []

        if self.store_name is None:
            reasons.append("store_missing")

        if self.transaction_date is None:
            reasons.append("date_missing")

        if self.total_amount is None:
            reasons.append("total_missing")

        return reasons


class ReceiptItemData(BaseModel):
    """Step 2: 品目1行分"""

    model_config = ConfigDict(extra="forbid")

    item_name: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="商品名",
    )
    quantity: Decimal | None = Field(
        default=None,
        max_digits=12,
        decimal_places=3,
        description="数量",
    )
    unit_price: Decimal | None = Field(
        default=None,
        max_digits=14,
        decimal_places=2,
        description="単価",
    )
    line_amount: Decimal | None = Field(
        default=None,
        max_digits=14,
        decimal_places=2,
        description="行金額",
    )
    tax_rate: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
        description="税率。百分率",
    )
    raw_text: str | None = Field(
        default=None,
        max_length=2048,
        description="該当行のOCR原文",
    )


class ReceiptItemsData(BaseModel):
    """Step 2: 品目一覧"""

    model_config = ConfigDict(extra="forbid")

    items: list[ReceiptItemData] = Field(
        default_factory=list,
        max_length=1000,
        description="商品明細のみ",
    )

    def review_reasons(self) -> list[str]:
        reasons: list[str] = []

        if not self.items:
            reasons.append("items_missing")

        if any(item.line_amount is None for item in self.items):
            reasons.append("item_amount_missing")

        return reasons


class ReceiptData(BaseModel):
    """Step 1とStep 2を統合した保存用データ"""

    model_config = ConfigDict(extra="forbid")

    header: ReceiptHeaderData
    items: list[ReceiptItemData]

    @property
    def review_reasons(self) -> list[str]:
        reasons = self.header.review_reasons()

        if not self.items:
            reasons.append("items_missing")

        if any(item.line_amount is None for item in self.items):
            reasons.append("item_amount_missing")

        if (
            self.header.total_amount is not None
            and self.items
            and all(item.line_amount is not None for item in self.items)
        ):
            item_sum = sum(
                (item.line_amount for item in self.items),
                Decimal("0"),
            )

            if item_sum != self.header.total_amount:
                reasons.append(
                    "item_sum_differs_from_total_check_tax_discounts"
                )

        return reasons