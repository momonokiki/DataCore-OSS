from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

class ParsedTransactionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_index: int
    transaction_date: date
    amount: Decimal
    description: str
    category_raw: str | None = None
    raw_row: dict

class ParsedCsvResultSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    account_number: str | None = None
    total_records: int
    total_amount: Decimal
    raw_header: dict
    transactions: list[ParsedTransactionSchema] = Field(default_factory=list)

