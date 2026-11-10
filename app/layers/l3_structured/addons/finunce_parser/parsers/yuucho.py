import csv
from datetime import datetime
from decimal import Decimal
from app.layers.l3_structured.addons.finunce_parser.parsers.base import BaseCsvParser
from app.layers.l3_structured.addons.finunce_parser.schemas import ParsedCsvResultSchema, ParsedTransactionSchema

class YuchoBankCsvParser(BaseCsvParser):
    parser_id = "yucho-csv-v1.0"
    account_id = "yucho_bank"

    def can_parse(self, content_bytes: bytes) -> bool:
        try:
            text = content_bytes[:512].decode("cp932", errors="ignore")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return lines[0].startswith("お客さま口座情報") or any("入出金明細ＩＤ" in line for line in lines[:10])
        except Exception:
            return False

    def parse(self, content_bytes: bytes) -> ParsedCsvResultSchema:
        text = content_bytes.decode("cp932")
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        raw_header = {}
        account_number = None
        transactions = []
        data_start_idx = -1

        for i, line in enumerate(lines):
            if line.startswith("お客さま口座番号："):
                account_number = line.replace("お客さま口座番号：", "").strip()
            elif line.startswith("取引日,入出金明細ＩＤ"):
                data_start_idx = i + 1
                break

        if data_start_idx == -1:
            raise ValueError("ゆうちょ銀行CSVの明細ヘッダーが見つかりませんでした。")

        total_amount = Decimal("0")
        reader = csv.reader(lines[data_start_idx:])
        for row_idx, row in enumerate(reader, start=1):
            if not row or len(row) < 6:
                continue

            dt = datetime.strptime(row[0], "%Y%m%d").date()
            income = Decimal(row[2]) if row[2] else Decimal("0")
            expense = Decimal(row[3]) if row[3] else Decimal("0")
            amount = income - expense
            total_amount += amount

            desc = " ".join(filter(None, [row[4].strip(), row[5].strip()]))

            transactions.append(ParsedTransactionSchema(
                row_index=row_idx, transaction_date=dt, amount=amount,
                description=desc, category_raw=row[4].strip() or None,
                raw_row={
                    "dt": row[0], "tx_id": row[1], "income": row[2], 
                    "expense": row[3], "detail1": row[4], "detail2": row[5], "balance": row[6] if len(row) > 6 else ""
                }
            ))

        return ParsedCsvResultSchema(
            account_id=self.account_id, account_number=account_number,
            total_records=len(transactions), total_amount=total_amount,
            raw_header=raw_header, transactions=transactions
        )

