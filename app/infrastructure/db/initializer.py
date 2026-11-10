
import os
import uuid
import importlib

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings

from app.infrastructure.db.base import Base
from app.infrastructure.db.session import sync_engine

# 全コアモデルをBase.metadataへ登録
import app.db_all_models  # noqa: F401

from app.infrastructure.db.models.l2_tools import L2Tool
from app.infrastructure.db.models.l3_tools import L3Tool

from app.infrastructure.db.seeds.tools_seed import (
    DEFAULT_L2_TOOLS,
    DEFAULT_L3_TOOLS,
)

from app.layers.l2_extracted.ocr.registry import OCR_PLUGINS


def sync_ocr_plugins(session: Session) -> None:
    """
    OCR Registryの情報をl2_toolsへ同期する。

    RegistryがOCRプラグインの定義元。
    この関数がDB登録・更新の責任を持つ。

    既存レコードのUUIDは変更しない。
    """

    print("=== OCR Plugin Registry Synchronization ===")

    for plugin in OCR_PLUGINS.values():

        tool_data = {
            "name": plugin.tool_name,
            "tool_type": "ocr",
            "description": plugin.description,
            "model_name": plugin.model_name,
            "model_version": plugin.tool_version,
            "config_json": {
                "supported_mimetypes": plugin.supported_mimetypes,
            },
        }

        existing = (
            session.query(L2Tool)
            .filter_by(name=plugin.tool_name)
            .first()
        )

        if existing is None:

            new_tool = L2Tool(
                id=uuid.uuid4(),
                **tool_data,
            )

            session.add(new_tool)

            print(
                f"[OCR Registry] Inserted L2Tool: {plugin.tool_name}"
            )

        else:

            # Registryが管理する項目だけを更新する。
            # id / output_dim / precision_typeは変更しない。
            existing.tool_type = tool_data["tool_type"]
            existing.description = tool_data["description"]
            existing.model_name = tool_data["model_name"]
            existing.model_version = tool_data["model_version"]
            existing.config_json = tool_data["config_json"]

            print(
                f"[OCR Registry] Updated L2Tool: {plugin.tool_name}"
            )


def run_database_initializer(session: Session) -> None:
    """
    1. ENABLED_L3_ADDONSに基づくL3アドオンモデルのロード
    2. データベーステーブルの作成
    3. アドオンテーブルのカラム追加
    4. OCR RegistryのDB同期
    5. L2/L3固定シードの投入
    """

    print("=== Database Initialization & Addon Loading ===")

    # 1. L3アドオンの動的ロード
    enabled_addons_env = settings.ENABLED_L3_ADDONS

    target_addons = [
        a.strip()
        for a in enabled_addons_env.split(",")
        if a.strip()
    ]

    for addon_name in target_addons:

        try:
            module_path = (
                f"app.layers.l3_structured.addons."
                f"{addon_name}.models"
            )

            importlib.import_module(module_path)

            print(
                f"-> L3 アドオンモデルをロードしました: {addon_name}"
            )

        except ModuleNotFoundError:
            print(
                f"【警告】L3 アドオン '{addon_name}' の "
                "models.py が見つかりません。"
            )

        except Exception as e:
            print(
                f"【エラー】L3 アドオン '{addon_name}' "
                f"のロードに失敗しました: {e}"
            )
            raise

    # 2. テーブルの自動作成
    Base.metadata.create_all(bind=sync_engine)

    print(
        "-> データベースのテーブル検証・作成が完了しました。"
    )

    # 2.5 addon_テーブルのカラム追加
    inspector = inspect(sync_engine)

    for table_name, table_obj in Base.metadata.tables.items():

        if not table_name.startswith("addon_"):
            continue

        existing_columns = [
            c["name"]
            for c in inspector.get_columns(table_name=table_name)
        ]

        for column in table_obj.columns:

            if column.name in existing_columns:
                continue

            type_compile = column.type.compile(
                dialect=sync_engine.dialect
            )

            null_str = (
                "NULL"
                if column.nullable
                else "NOT NULL"
            )

            alter_query = (
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {column.name} "
                f"{type_compile} {null_str}"
            )

            session.execute(text(alter_query))

            print(
                f"[Addon Migration] Added column "
                f"'{column.name}' ({type_compile}) "
                f"to {table_name}"
            )

    # 3. OCR Registryの同期
    sync_ocr_plugins(session)

    # 4. OCR以外のL2固定シード
    for tool_data in DEFAULT_L2_TOOLS:

        existing = (
            session.query(L2Tool)
            .filter_by(name=tool_data["name"])
            .first()
        )

        if existing is None:
            session.add(L2Tool(**tool_data))

            print(
                f"[Seed] Inserted L2Tool: {tool_data['name']}"
            )

        else:
            print(
                f"[Seed] L2Tool already exists: {tool_data['name']}"
            )

    # 5. L3固定シード
    for tool_data in DEFAULT_L3_TOOLS:

        existing = (
            session.query(L3Tool)
            .filter_by(name=tool_data["name"])
            .first()
        )

        if existing is None:
            session.add(L3Tool(**tool_data))

            print(
                f"[Seed] Inserted L3Tool: {tool_data['name']}"
            )

        else:
            print(
                f"[Seed] L3Tool already exists: {tool_data['name']}"
            )

    session.commit()

    print(
        "=== 初期化プロセスが正常に完了しました ==="
    )


if __name__ == "__main__":

    from app.infrastructure.db.session import get_sync_db_session

    print(
        "--- データベース初期化スクリプト単体実行 ---"
    )

    with get_sync_db_session() as session:
        run_database_initializer(session)

