from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ReceiptExperimentItemData(BaseModel):
    """
    実験用レシート商品データ。

    本番DBのモデルとは独立させる。
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    item_name: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="購入した商品の名称",
    )

    quantity: float | None = Field(
        default=None,
        gt=0,
        description=(
            "購入数量。レシート上に明示されている場合のみ設定する。"
            "不明な場合はnull"
        ),
    )

    price: int | None = Field(
        default=None,
        ge=0,
        description=(
            "その商品の購入金額。"
            "単価ではなく、数量分を含む商品行の合計金額。"
            "対応する金額が不明な場合はnull"
        ),
    )


class ReceiptExperimentItemsData(BaseModel):
    """
    実験用レシート商品一覧。
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    items: list[ReceiptExperimentItemData] = Field(
        default_factory=list,
        max_length=1000,
        description="購入した商品の一覧",
    )