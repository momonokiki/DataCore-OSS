import argparse
import json
import uuid
import app.db_all_models
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.infrastructure.db.session import get_sync_db_session
from .models import ReceiptTotal

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt_id")
    args = parser.parse_args()
    with get_sync_db_session() as session:
        receipt = session.execute(select(ReceiptTotal).where(
            ReceiptTotal.id == uuid.UUID(args.receipt_id)
        ).options(selectinload(ReceiptTotal.items))).scalar_one()
        output = {c.name: str(getattr(receipt, c.name)) if getattr(receipt, c.name) is not None else None
                  for c in ReceiptTotal.__table__.columns if c.name != "raw_payload"}
        output["items"] = [{c.name: str(getattr(item, c.name)) if getattr(item, c.name) is not None else None
                            for c in item.__table__.columns}
                           for item in sorted(receipt.items, key=lambda i: i.line_number)]
        print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
