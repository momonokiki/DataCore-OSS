import uuid
import app.db_all_models  # SQLAlchemyマッピングのインポート関係を解決
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.infrastructure.db.session import sync_engine, get_sync_db_session
from app.infrastructure.db.models.l3_tools import L3Tool
from app.layers.l3_structured.addons.finunce_parser.models import AccountStatement, StatementTransaction
from app.layers.l3_structured.addons.finunce_parser.parsers.registry import ParserRegistry
from app.layers.l3_structured.addons.finunce_parser.service import get_tool_name_for_account

def main():
    print("Initializing Kakeisys Financial Statement DB Tables...")
    with sync_engine.begin() as connection:
        AccountStatement.__table__.create(connection, checkfirst=True)
        StatementTransaction.__table__.create(connection, checkfirst=True)

    registry = ParserRegistry()
    
    with get_sync_db_session() as session:
        # 登録されている全パーサを走査し、個別のL3Toolレコードを生成
        for parser in registry.parsers:
            tool_name = get_tool_name_for_account(parser.account_id)
            
            session.execute(
                insert(L3Tool).values(
                    id=uuid.uuid4(),
                    name=tool_name,
                    model_name="deterministic_csv_parser",
                    prompt_version=parser.parser_id,  # パーサの固有バージョンを管理
                    config={"provider": "kakeisys", "target_account": parser.account_id},
                    is_active=True,
                ).on_conflict_do_nothing(index_elements=[L3Tool.name])
            )
            
            # 不変履歴（データプロベナンス）に反する上書きが無いか確認
            tool = session.execute(select(L3Tool).where(L3Tool.name == tool_name)).scalar_one()
            if tool.prompt_version != parser.parser_id:
                raise ValueError(f"Provenance mismatch for tool '{tool_name}'. Code version has been updated without updating tool records.")
                
            print(f"-> L3 Tool Configured: [ {tool_name} ] (Internal Version: {parser.parser_id})")

    print("All financial parser tables and tools are fully configured.")

if __name__ == "__main__":
    main()

