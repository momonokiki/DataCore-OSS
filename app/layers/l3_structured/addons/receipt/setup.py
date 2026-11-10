
from __future__ import annotations

import argparse
import uuid

# DBモデルの登録漏れを防ぐためのimport
import app.db_all_models  # noqa: F401

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.db.session import (
    sync_engine,
    get_sync_db_session,
)
from app.infrastructure.db.models.l3_tools import L3Tool

from .models import ReceiptTotal, ReceiptItem
from .parser import PROMPT_VERSION
from .service import DEFAULT_TOOL_NAME


EXPECTED_CONFIG = {
    "provider": "ollama",
    "addon": "receipt",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Initialize receipt addon tables and parser tool."
    )

    parser.add_argument(
        "--model",
        default=None,
        help="Installed Ollama model name.",
    )

    parser.add_argument(
        "--tool-name",
        default=None,
        help=f"L3Tool name (default: {DEFAULT_TOOL_NAME}).",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation.",
    )

    return parser.parse_args()


def prompt_value(label: str, default: str | None = None) -> str:
    if default:
        value = input(f"{label} [{default}]: ").strip()
        return value or default

    while True:
        value = input(f"{label}: ").strip()

        if value:
            return value

        print("入力してください。")


def get_settings(args) -> tuple[str, str]:

    # 引数が指定されていない場合は対話入力
    if args.model is None or args.tool_name is None:
        if not __import__("sys").stdin.isatty():
            raise RuntimeError(
                "対話入力できません。"
                "--model と --tool-name を指定してください。"
            )

    model = (
        args.model
        if args.model
        else prompt_value("Ollama model")
    )

    tool_name = (
        args.tool_name
        if args.tool_name
        else prompt_value(
            "L3Tool name",
            DEFAULT_TOOL_NAME,
        )
    )

    return model, tool_name


def confirm_settings(
    model: str,
    tool_name: str,
    skip: bool = False,
) -> bool:

    print()
    print("========================================")
    print("Receipt addon setup")
    print("========================================")
    print(f"Model         : {model}")
    print(f"Tool name     : {tool_name}")
    print(f"Prompt version: {PROMPT_VERSION}")
    print(f"Config        : {EXPECTED_CONFIG}")
    print("----------------------------------------")
    print("Operations:")
    print("  - Create receipt tables if not exist")
    print("  - Register parser tool if not exist")
    print("  - Never alter existing table schemas")
    print("  - Never overwrite existing tool settings")
    print("========================================")

    if skip:
        return True

    answer = input("Continue? [y/N]: ").strip().lower()

    return answer in ("y", "yes")


def create_tables():

    print("-> Creating receipt tables...")

    with sync_engine.begin() as connection:
        ReceiptTotal.__table__.create(
            connection,
            checkfirst=True,
        )

        ReceiptItem.__table__.create(
            connection,
            checkfirst=True,
        )

    print("-> Receipt tables are ready.")


def register_tool(
    model: str,
    tool_name: str,
):

    print("-> Registering receipt parser tool...")

    with get_sync_db_session() as session:

        session.execute(
            insert(L3Tool)
            .values(
                id=uuid.uuid4(),
                name=tool_name,
                model_name=model,
                prompt_version=PROMPT_VERSION,
                config=EXPECTED_CONFIG,
                is_active=True,
            )
            .on_conflict_do_nothing(
                index_elements=[L3Tool.name]
            )
        )

        tool = session.execute(
            select(L3Tool).where(
                L3Tool.name == tool_name
            )
        ).scalar_one()

        # 既存設定を変更しないための整合性確認
        if (
            tool.model_name != model
            or tool.prompt_version != PROMPT_VERSION
            or tool.config != EXPECTED_CONFIG
        ):
            raise ValueError(
                "\nExisting tool configuration differs.\n"
                f"Tool name     : {tool_name}\n"
                f"Existing model: {tool.model_name}\n"
                f"Requested model: {model}\n"
                f"Existing prompt version: {tool.prompt_version}\n"
                f"Requested prompt version: {PROMPT_VERSION}\n"
                "Existing configuration will not be overwritten.\n"
                "Choose another --tool-name to register a new version."
            )

    print("-> Receipt parser tool is ready.")


def main():

    args = parse_args()

    print()
    print("=== Receipt addon setup ===")

    # 1. 設定入力
    model, tool_name = get_settings(args)

    # 2. 実行確認
    if not confirm_settings(
        model,
        tool_name,
        skip=args.yes,
    ):
        print("-> Setup cancelled.")
        return

    # 3. テーブル作成
    create_tables()

    # 4. ツール登録
    register_tool(
        model=model,
        tool_name=tool_name,
    )

    print()
    print("========================================")
    print("Receipt addon setup completed.")
    print("========================================")


if __name__ == "__main__":
    main()

