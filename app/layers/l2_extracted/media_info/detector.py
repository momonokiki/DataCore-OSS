from dataclasses import dataclass


from app.layers.l2_extracted.media_info.inspectors.binary import (
    BinaryInspector,
)
from app.layers.l2_extracted.media_info.inspectors.text import (
    TextInspector,
)


@dataclass(frozen=True)
class DetectionResult:
    mime_type: str
    detected: bool
    detection_method: str


class MediaTypeDetector:
    UNKNOWN_MIME_TYPE = "application/octet-stream"

    def __init__(self):
        self.binary_inspector = BinaryInspector()
        self.text_inspector = TextInspector()

    def detect(
        self,
        file_content: bytes,
        filename: str | None = None,
    ) -> DetectionResult:
        if not file_content:
            return DetectionResult(
                mime_type=self.UNKNOWN_MIME_TYPE,
                detected=False,
                detection_method="none",
            )

        extension = self._get_extension(filename)

        # 1. バイナリ形式の判定
        # 拡張子に関係なく、実データのマジックバイトを優先する
        binary_result = self.binary_inspector.inspect(
            file_content,
            extension,
        )

        if binary_result:
            return DetectionResult(
                mime_type=binary_result,
                detected=True,
                detection_method="binary",
            )

        # 2. テキスト形式の判定
        # 拡張子は判定の補助情報として使用する
        text_result = self.text_inspector.inspect(
            file_content,
            extension,
        )

        if text_result:
            return DetectionResult(
                mime_type=text_result,
                detected=True,
                detection_method="text",
            )

        return DetectionResult(
            mime_type=self.UNKNOWN_MIME_TYPE,
            detected=False,
            detection_method="none",
        )

    @staticmethod
    def _get_extension(filename: str | None) -> str | None:
        if not filename:
            return None

        # Windows形式のパス区切りにも対応
        normalized_filename = filename.replace("\\", "/")
        basename = normalized_filename.rsplit("/", 1)[-1]

        if "." not in basename:
            return None

        extension = basename.rsplit(".", 1)[-1]

        if not extension:
            return None

        return f".{extension.lower()}"
