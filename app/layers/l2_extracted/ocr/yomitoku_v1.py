
import os
import tempfile
from typing import Dict, Any, List, Tuple

import cv2
import numpy as np

from app.layers.l2_extracted.ocr.base import (
    BaseOcrPlugin,
    OcrPluginResponse,
)


class YomitokuV1Plugin(BaseOcrPlugin):
    """
    YomiToku OCRエンジンを駆動するL2プラグイン。

    原本バイナリから画像を読み込み、ドキュメント解析を実行する。
    Markdownテキストと単語座標を共通形式に正規化して返却する。
    """

    _shared_reader = None
    _yomitoku_class = None

    def __init__(self):
        pass

    def _get_reader(self):
        if YomitokuV1Plugin._shared_reader is None:
            print(
                f"[YomiToku] Initializing model pid={os.getpid()}",
                flush=True,
            )

            # OCR実行時に初めてYomiTokuをインポートする
            if YomitokuV1Plugin._yomitoku_class is None:
                try:
                    import yomitoku

                    if hasattr(yomitoku, "DocumentAnalyzer"):
                        YomitokuV1Plugin._yomitoku_class = (
                            yomitoku.DocumentAnalyzer
                        )
                    elif hasattr(yomitoku, "Yomitoku"):
                        YomitokuV1Plugin._yomitoku_class = yomitoku.Yomitoku
                    elif hasattr(yomitoku, "OCR"):
                        YomitokuV1Plugin._yomitoku_class = yomitoku.OCR

                except ImportError as e:
                    raise RuntimeError(
                        "yomitokuライブラリが導入されていません。"
                    ) from e

            if YomitokuV1Plugin._yomitoku_class is None:
                raise RuntimeError(
                    "対応するYomiTokuクラスを取得できません。"
                )

            YomitokuV1Plugin._shared_reader = (
                YomitokuV1Plugin._yomitoku_class()
            )

            print(
                f"[YomiToku] Model initialized pid={os.getpid()}",
                flush=True,
            )

        return YomitokuV1Plugin._shared_reader

    @property
    def tool_name(self) -> str:
        return "yomitoku_ocr"

    @property
    def tool_version(self) -> str:
        return "1.0.0"

    @property
    def model_name(self) -> str:
        return "yomitoku"

    @property
    def description(self) -> str:
        return "YomiToku OCRエンジン（Markdown・単語座標正規化）"

    @property
    def supported_mimetypes(self) -> List[str]:
        return ["image/jpeg", "image/png", "image/webp"]

    @staticmethod
    def _rotate_image(
        image: np.ndarray,
        angle: int,
    ) -> np.ndarray:
        """画像を指定角度だけ回転する。"""
        if angle == 0:
            return image
        elif angle == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        elif angle == 270:
            return cv2.rotate(
                image,
                cv2.ROTATE_90_COUNTERCLOCKWISE,
            )

        return image

    @staticmethod
    def _normalize_result(result: Any) -> Dict[str, Any]:
        """外部エンジンの戻り値を共通辞書形式に正規化する。"""

        text = ""
        score = 0.0
        points = []

        if isinstance(result, dict):
            text = result.get(
                "text",
                result.get("content", ""),
            )

            score = result.get(
                "score",
                result.get(
                    "confidence",
                    result.get("rec_score", 0.0),
                ),
            )

            points = result.get(
                "points",
                result.get("box", result.get("bbox", [])),
            )

        elif hasattr(result, "content"):
            text = getattr(result, "content", "")
            score = getattr(result, "rec_score", 0.0)
            points = getattr(result, "points", [])

        elif hasattr(result, "points"):
            points = getattr(result, "points", [])
            text = getattr(result, "text", "")
            score = getattr(result, "score", 0.0)

        if text is None:
            text = ""

        if isinstance(score, np.generic):
            score = score.item()

        try:
            score = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0

        if isinstance(points, np.ndarray):
            points = points.tolist()
        elif hasattr(points, "tolist") and not isinstance(points, list):
            points = points.tolist()

        if points is None:
            points = []

        return {
            "text": str(text),
            "score": score,
            "points": points,
        }

    @classmethod
    def _sort_results(
        cls,
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """座標を利用して、単語を行単位の読み順に並び替える。"""

        if not results:
            return []

        def get_metrics(
            item: Dict[str, Any],
        ) -> Tuple[float, float, float]:

            pts = item.get("points", [])

            if pts is None:
                return 0.0, 0.0, 0.0

            try:
                points_array = np.asarray(pts, dtype=float)

                if points_array.size < 2:
                    return 0.0, 0.0, 0.0

                points_array = points_array.reshape(-1, 2)

                xs = points_array[:, 0]
                ys = points_array[:, 1]

                return (
                    float((np.min(ys) + np.max(ys)) / 2.0),
                    float(np.min(xs)),
                    float(np.max(ys) - np.min(ys)),
                )

            except (TypeError, ValueError, IndexError):
                return 0.0, 0.0, 0.0

        mapped = [
            {
                "data": item,
                "metrics": get_metrics(item),
            }
            for item in results
        ]

        mapped.sort(key=lambda x: x["metrics"][0])

        sorted_data = []
        current_line = []

        for curr in mapped:
            if not current_line:
                current_line.append(curr)
                continue

            prev = current_line[-1]

            y_curr, _, h_curr = curr["metrics"]
            y_prev, _, h_prev = prev["metrics"]

            h_avg = (
                (h_curr + h_prev) / 2.0
                if (h_curr + h_prev) > 0
                else 10.0
            )

            if abs(y_curr - y_prev) < (h_avg * 0.5):
                current_line.append(curr)
            else:
                current_line.sort(
                    key=lambda x: x["metrics"][1]
                )

                sorted_data.extend(
                    [x["data"] for x in current_line]
                )

                current_line = [curr]

        if current_line:
            current_line.sort(
                key=lambda x: x["metrics"][1]
            )

            sorted_data.extend(
                [x["data"] for x in current_line]
            )

        return sorted_data

    def _to_markdown(self, analyze_result: Any) -> str:
        """YomiTokuの解析結果をMarkdownへ変換する。"""

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
            prefix="yomitoku_"
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
                "YomiTokuがMarkdown文字列を返さず、"
                "出力ファイルも生成されませんでした。"
            )

    def process_from_memory(
        self,
        file_content: bytes,
        mime_type: str,
    ) -> OcrPluginResponse:

        """メモリ上の原本バイナリからOCRを実行する。"""

        nparr = np.frombuffer(file_content, np.uint8)

        img = cv2.imdecode(
            nparr,
            cv2.IMREAD_COLOR,
        )

        if img is None:
            raise ValueError(
                "生バイナリから画像へのデコードに失敗しました。"
                "破損ファイルの可能性があります。"
            )

        reader = self._get_reader()

        # 画像を2倍に拡大
        h, w = img.shape[:2]

        processed_img = cv2.resize(
            img,
            (w * 2, h * 2),
            interpolation=cv2.INTER_CUBIC,
        )

        # ドキュメント解析
        try:
            inference_out = reader(processed_img)

            if isinstance(inference_out, (list, tuple)):
                if not inference_out:
                    raise ValueError(
                        "yomitokuの推論結果が空のリスト／タプルです。"
                    )

                analyze_result = inference_out[0]
            else:
                analyze_result = inference_out

            if analyze_result is None:
                raise ValueError(
                    "yomitokuの解析結果本体がNoneです。"
                )

        except Exception as e:
            raise RuntimeError(
                f"yomitokuによるドキュメント解析に失敗しました: {e}"
            ) from e

        # 単語座標データを正規化
        if hasattr(analyze_result, "words"):
            source_words = analyze_result.words
        elif isinstance(analyze_result, dict):
            source_words = analyze_result.get("words", [])
        elif isinstance(analyze_result, (list, tuple)):
            source_words = analyze_result
        else:
            source_words = []

        if source_words is None:
            source_words = []

        normalized = [
            self._normalize_result(item)
            for item in source_words
        ]

        text_results = [
            item
            for item in normalized
            if item["text"].strip()
        ]

        filtered = [
            item
            for item in text_results
            if item["points"]
        ]

        sorted_words = self._sort_results(filtered)

        # Markdown取得
        try:
            full_text = self._to_markdown(analyze_result)
            output_mode = "yomitoku_native_markdown"

        except Exception as e:
            print(
                "[Yomitoku] Markdown conversion failed; "
                f"falling back to OCR words: {type(e).__name__}: {e}",
                flush=True,
            )

            fallback_words = self._sort_results(text_results)

            full_text = "\n".join(
                item["text"]
                for item in fallback_words
            )

            output_mode = "normalized_words_fallback"

        return {
            "full_text": full_text,
            "words": sorted_words,
            "metadata_json": {
                "tool_name": self.tool_name,
                "tool_version": self.tool_version,
                "output_mode": output_mode,
            },
        }

