import argparse
import uuid
import app.db_all_models
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.infrastructure.db.session import sync_engine, get_sync_db_session
from app.infrastructure.db.models.l3_tools import L3Tool
from .models import ReceiptTotal, ReceiptItem
from .parser import PROMPT_VERSION
from .service import DEFAULT_TOOL_NAME

def main():
    parser = argparse.ArgumentParser(description="Create only receipt tables and register an immutable parser configuration")
    parser.add_argument("--model", required=True, help="An already installed Ollama model supporting structured output")
    parser.add_argument("--tool-name", default=DEFAULT_TOOL_NAME)
    args = parser.parse_args()
    with sync_engine.begin() as connection:
        ReceiptTotal.__table__.create(connection, checkfirst=True)
        ReceiptItem.__table__.create(connection, checkfirst=True)
    with get_sync_db_session() as session:
        session.execute(insert(L3Tool).values(
            id=uuid.uuid4(), name=args.tool_name, model_name=args.model,
            prompt_version=PROMPT_VERSION, config={"provider": "ollama", "addon": "receipt"}, is_active=True,
        ).on_conflict_do_nothing(index_elements=[L3Tool.name]))
        tool = session.execute(select(L3Tool).where(L3Tool.name == args.tool_name)).scalar_one()
        if tool.model_name != args.model or tool.prompt_version != PROMPT_VERSION:
            raise ValueError("Existing tool configuration differs; choose a new --tool-name instead of rewriting provenance")
    print("Receipt tables and parser tool are ready. Existing table schemas are not altered.")

if __name__ == "__main__":
    main()
