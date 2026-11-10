
from app.layers.l2_extracted.ocr.base import BaseOcrPlugin
from app.layers.l2_extracted.ocr.yomitoku_v1 import YomitokuV1Plugin
from app.layers.l2_extracted.ocr.yomitoku_native_v1 import (
    YomitokuNativeV1Plugin,
)


# 利用可能なOCRプラグインの一覧
#
# 新しいOCRプラグインを追加する場合は、
# ここにインスタンスを1つ追加する。
#
# DB登録はinitializer.pyが担当する。
# 実際のOCR実行はservice.pyが担当する。

OCR_PLUGINS: dict[str, BaseOcrPlugin] = {
#    "yomitoku_ocr": YomitokuV1Plugin(),
    "yomitoku_native_ocr": YomitokuNativeV1Plugin(),
}
