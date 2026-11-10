import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.models.l3_tools import L3Tool
from app.layers.l3_structured.addons.finunce_parser.models import AccountStatement, StatementTransaction
from app.layers.l3_structured.addons.finunce_parser.parsers.registry import ParserRegistry

def get_tool_name_for_account(account_id: str) -> str:
    """金融機関アカウント固有のL3Tool名を生成"""
    return f"kakeibo_csv_{account_id}"

async def parse_financial_csv(
    session: AsyncSession,
    file_hash: str,
    file_bytes: bytes,
) -> dict:
    """
    L1のファイルデータを直接受け取り、金融機関を判定した上で
    各パーサ用に独立管理されたL3Toolレコードに紐づけて確定的パース・保存を行う（L2バイパス）
    """
    base = {"file_hash": file_hash}
    registry = ParserRegistry()
    
    # 1. バイナリシグネチャから適切なパーサを自動判定
    parser = registry.select_parser(file_bytes)
    if parser is None:
        return {**base, "status": "skipped", "reason": "unsupported_csv_format"}

    # アカウント毎に個別のTool名を解決
    target_plugin_name = get_tool_name_for_account(parser.account_id)

    try:
        # 2. 独立したTool定義の存在確認と冪等性チェック (トランザクション1)
        async with session.begin():
            tool = (await session.execute(
                select(L3Tool).where(L3Tool.name == target_plugin_name)
            )).scalar_one_or_none()

            if tool is None:
                raise ValueError(f"Parser tool '{target_plugin_name}' is not registered; run setup script first")

            if not tool.is_active:
                return {**base, "status": "skipped", "reason": "parser_disabled"}

            if tool.prompt_version != parser.parser_id:
                raise ValueError(f"Parser version mismatch for {target_plugin_name}")

            # 同一ハッシュ、かつ同一Toolでの処理が完了しているか検証
            existing = (await session.execute(
                select(AccountStatement).where(
                    AccountStatement.file_hash == file_hash,
                    AccountStatement.parser_tool_id == tool.id
                )
            )).scalar_one_or_none()

            if existing:
                return {**base, "status": "already_exists", "statement_id": str(existing.id)}

            tool_id = tool.id

        # 3. 確定的なCSVパースの実行
        parsed_data = parser.parse(file_bytes)

        # 4. 同一トランザクション内でのリレーショナルデータの一括永続化 (トランザクション2)
        async with session.begin():
            statement = AccountStatement(
                id=uuid.uuid4(),
                file_hash=file_hash,
                parser_tool_id=tool_id,
                account_id=parsed_data.account_id,
                account_number=parsed_data.account_number,
                total_records=parsed_data.total_records,
                total_amount=parsed_data.total_amount,
                raw_header=parsed_data.raw_header
            )

            statement.transactions = [
                StatementTransaction(
                    row_index=tx.row_index,
                    transaction_date=tx.transaction_date,
                    amount=tx.amount,
                    description=tx.description,
                    category_raw=tx.category_raw,
                    raw_row=tx.raw_row
                )
                for tx in parsed_data.transactions
            ]

            session.add(statement)
            await session.flush()
            statement_id = str(statement.id)

        return {
            **base,
            "status": "success",
            "account_id": parser.account_id,
            "statement_id": statement_id,
            "record_count": parsed_data.total_records
        }

    except Exception:
        await session.rollback()
        raise

