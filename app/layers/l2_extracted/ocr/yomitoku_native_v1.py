
from __future__ import annotations

import os
import tempfile
from typing import Any

import cv2
import numpy as np

from app.layers.l2_extracted.ocr.base import (
    BaseOcrPlugin,
    OcrPluginResponse,
)


class YomitokuNativeV1Plugin(BaseOcrPlugin):
    """
    YomiTokuのネイティブ解析結果を保持するL2 OCRプラグイン。

    - 原画像の解像度を変更しない
    - 独自の回転処理を行わない
    - 単語の読み順を並べ替えない
    - YomiTokuのMarkdownをcontent_textに保存する
    - words / paragraphs / tablesをmetadataとして保持する
    """

    _shared_reader = None
    _yomitoku_class = None

    def __init__(self):
        pass

    @property
    def tool_name(self) -> str:
        return "yomitoku_native_ocr"

    @property
    def tool_version(self) -> str:
        return "1.0.0"

    @property
    def model_name(self) -> str:
        return "yomitoku"

    @property
    def description(self) -> str:
        return "YomiToku OCRエンジン（ネイティブ解析結果・Markdown保持）"

    @property
    def supported_mimetypes(self) -> list[str]:
        return [
            "image/jpeg",
            "image/png",
            "image/webp",
        ]

    def _get_reader(self):
        if YomitokuNativeV1Plugin._shared_reader is None:

            if YomitokuNativeV1Plugin._yomitoku_class is None:
                try:
                    import yomitoku

                    YomitokuNativeV1Plugin._yomitoku_class = getattr(
                        yomitoku,
                        "DocumentAnalyzer",
                        None,
                    )

                    if YomitokuNativeV1Plugin._yomitoku_class is None:
                        YomitokuNativeV1Plugin._yomitoku_class = getattr(
                            yomitoku,
                            "Yomitoku",
                            None,
                        )

                    if YomitokuNativeV1Plugin._yomitoku_class is None:
                        YomitokuNativeV1Plugin._yomitoku_class = getattr(
                            yomitoku,
                            "OCR",
                            None,
                        )

                except ImportError as e:
                    raise RuntimeError(
                        "yomitokuライブラリが導入されていないか、"
                        "対応するクラスをインポートできません。"
                    ) from e

            if YomitokuNativeV1Plugin._yomitoku_class is None:
                raise RuntimeError(
                    "対応するYomiTokuクラスを取得できません。"
                )

            print(
                "[YomiToku Native] Initializing model "
                f"pid={os.getpid()}",
                flush=True,
            )

            YomitokuNativeV1Plugin._shared_reader = (
                YomitokuNativeV1Plugin._yomitoku_class()
            )

            print(
                "[YomiToku Native] Model initialized "
                f"pid={os.getpid()}",
                flush=True,
            )

        return YomitokuNativeV1Plugin._shared_reader

    @classmethod
    def _to_jsonable(cls, value: Any) -> Any:
        """YomiTokuの戻り値をJSONB保存可能なPython標準型へ変換する。"""

        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, np.generic):
            return cls._to_jsonable(value.item())

        if isinstance(value, np.ndarray):
            return cls._to_jsonable(value.tolist())

        if isinstance(value, dict):
            return {
                str(key): cls._to_jsonable(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple)):
            return [
                cls._to_jsonable(item)
                for item in value
            ]

        if hasattr(value, "model_dump"):
            return cls._to_jsonable(
                value.model_dump(mode="json")
            )

        if hasattr(value, "to_dict"):
            return cls._to_jsonable(value.to_dict())

        if hasattr(value, "__dict__"):
            return cls._to_jsonable(vars(value))

        if hasattr(value, "tolist"):
            return cls._to_jsonable(value.tolist())

        return str(value)

    @classmethod
    def _get_native_field(
        cls,
        result: Any,
        field_name: str,
    ) -> Any:

        if isinstance(result, dict):
            return result.get(field_name)

        return getattr(result, field_name, None)

    def _to_markdown(self, analyze_result: Any) -> str:
        """YomiToku標準のMarkdown出力を取得する。"""

        if isinstance(analyze_result, dict):
            markdown = analyze_result.get("markdown")

            if isinstance(markdown, str):
                return markdown

        to_markdown = getattr(
            analyze_result,
            "to_markdown",
            None,
        )

        if not callable(to_markdown):
            raise TypeError(
                "解析結果にto_markdown()メソッドがありません。"
            )

        with tempfile.TemporaryDirectory(
            prefix="yomitoku_native_"
        ) as temp_dir:

            output_path = os.path.join(
                temp_dir,
                "result.md",
            )

            markdown = to_markdown(
                output_path,
                export_figure=False,
            )

            if isinstance(markdown, str):
                return markdown

            if os.path.isfile(output_path):
                with open(
                    output_path,
                    "r",
                    encoding="utf-8",
                ) as file:
                    return file.read()

        raise RuntimeError(
            "YomiTokuがMarkdownを返さず、"
            "出力ファイルも生成されませんでした。"
        )

    def process_from_memory(
        self,
        file_content: bytes,
        mime_type: str,
    ) -> OcrPluginResponse:

        # 原本バイナリを画像へデコード
        nparr = np.frombuffer(
            file_content,
            np.uint8,
        )

        img = cv2.imdecode(
            nparr,
            cv2.IMREAD_COLOR,
        )

        if img is None:
            raise ValueError(
                "生バイナリから画像へのデコードに失敗しました。"
                "破損ファイルの可能性があります。"
            )

        # YomiTokuで解析
        reader = self._get_reader()

        try:
            inference_out = reader(img)

            if isinstance(inference_out, (list, tuple)):
                if not inference_out:
                    raise ValueError(
                        "YomiTokuの推論結果が空です。"
                    )

                analyze_result = inference_out[0]
            else:
                analyze_result = inference_out

            if analyze_result is None:
                raise ValueError(
                    "YomiTokuの解析結果がNoneです。"
                )

        except Exception as e:
            raise RuntimeError(
                f"YomiTokuの解析に失敗しました: {e}"
            ) from e

        # ネイティブ解析情報を取得
        source_words = self._get_native_field(
            analyze_result,
            "words",
        )

        source_paragraphs = self._get_native_field(
            analyze_result,
            "paragraphs",
        )

        source_tables = self._get_native_field(
            analyze_result,
            "tables",
        )

        # NumPy配列などの真偽値判定を避ける
        if source_words is None:
            source_words = []

        if source_paragraphs is None:
            source_paragraphs = []

        if source_tables is None:
            source_tables = []

        # JSONB保存可能な形式へ変換
        words = self._to_jsonable(source_words)
        paragraphs = self._to_jsonable(source_paragraphs)
        tables = self._to_jsonable(source_tables)

        # Markdown取得
        full_text = self._to_markdown(analyze_result)

        return {
            "full_text": full_text,
            "words": words,
            "metadata_json": {
                "tool_name": self.tool_name,
                "tool_version": self.tool_version,
                "engine": "yomitoku",
                "native_output": True,
                "image_width": int(img.shape[1]),
                "image_height": int(img.shape[0]),
                "words": words,
                "paragraphs": paragraphs,
                "tables": tables,
            },
        }

