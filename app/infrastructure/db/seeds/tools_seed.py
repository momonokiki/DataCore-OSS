
"""
L2Tool および L3Tool の初期シードデータ定義。

OCRプラグインはocr/registry.pyで管理するため、
ここでは固定シードとして管理するツールのみ定義する。
"""

from typing import Any, Dict, List


DEFAULT_L2_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "nomic_embed_text",
        "tool_type": "embedding",
        "description": "Ollama nomic-embed-text 埋め込みモデル",
        "output_dim": 768,
        "precision_type": "float32",
        "model_name": "nomic-embed-text",
        "model_version": "v1.5",
        "config_json": {
            "provider": "ollama",
        },
    },
]


DEFAULT_L3_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "receipt_parser_llama3.1:1b",
        "model_name": "llama3.2:1b",
        "prompt_version": "v1.0",
        "is_active": True,
        "config": {
            "doc_type": "receipt",
            "system_prompt": (
                "あなたはレシートの情報を正確に抽出するAIです。"
                "店舗名、取引日時、合計金額などを抽出してください。"
            ),
            "temperature": 0.0,
        },
    },
]

