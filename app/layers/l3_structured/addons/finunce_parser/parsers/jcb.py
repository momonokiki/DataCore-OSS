import csv
from datetime import datetime
from decimal import Decimal
from app.layers.l3_structured.addons.finunce_parser.parsers.base import BaseCsvParser
from app.layers.l3_structured.addons.finunce_parser.schemas import ParsedCsvResultSchema, ParsedTransactionSchema

class JcbCardCsvParser(BaseCsvParser):
    parser_id = "jcb-csv-v1.0"
    account_id = "jcb_card"

    def can_parse(self, content_bytes: bytes) -> bool:
        try:
            text = content_bytes[:1024].decode("cp932", errors="ignore")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return any("今回のお支払日" in line for line in lines[:10]) or any("【ご利用明細】" in line for line in lines[:10])
        except Exception:
            return False

    def parse(self, content_bytes: bytes) -> ParsedCsvResultSchema:
        text = content_bytes.decode("cp932", errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        raw_header = {}
        account_number = None
        transactions = []
        data_start_idx = -1

        for i, line in enumerate(lines):
            row = next(csv.reader([line]))
            if len(row) >= 4 and row[2]:
                key = row[2].strip()
                val = row[3].strip()
                if key == "今回のお支払日": raw_header["payment_date"] = val
                elif key == "今回のお支払金額合計(￥)": raw_header["total_payment_amount"] = int(val.replace(",", ""))

            if len(row) > 0 and row[0] == "ご利用者" and "ご利用日" in row:
                data_start_idx = i + 1
                break

        if data_start_idx == -1:
            raise ValueError("JCB CSVの明細ヘッダーが見つかりませんでした。")

        total_amount = Decimal("0")
        reader = csv.reader(lines[data_start_idx:])
        for row_idx, row in enumerate(reader, start=1):
            if not row or len(row) < 9 or not row[2].strip():
                continue

            dt = datetime.strptime(row[2].strip(), "%Y/%m/%d").date()
            clean_amt = Decimal((row[8].strip() or row[4].strip()).replace(",", ""))
            amount = -clean_amt  # 支出をマイナス値で表現
            total_amount += amount

            if not account_number and row[0].strip():
                account_number = row[0].strip().split()[0]

            desc = f"{row[3].strip()} ({row[10].strip()})" if row[10].strip() else row[3].strip()

            transactions.append(ParsedTransactionSchema(
                row_index=row_idx, transaction_date=dt, amount=amount,
                description=desc, category_raw=row[1].strip() or None,
                raw_row={
                    "user": row[0], "category": row[1], "dt": row[2], "desc": row[3], 
                    "amount": row[4], "pay_type": row[5], "times": row[6], "sign": row[7], 
                    "payment_amount": row[8], "loc": row[9], "memo": row[10], "remarks": row[11]
                }
            ))

        return ParsedCsvResultSchema(
            account_id=self.account_id, account_number=account_number,
            total_records=len(transactions), total_amount=total_amount,
            raw_header=raw_header, transactions=transactions
        )

