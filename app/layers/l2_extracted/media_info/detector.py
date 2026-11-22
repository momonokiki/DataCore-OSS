
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

    def detect(self, file_content: bytes) -> DetectionResult:
        if not file_content:
            return DetectionResult(
                mime_type=self.UNKNOWN_MIME_TYPE,
                detected=False,
                detection_method="none",
            )

        # 1. バイナリ形式の判定
        binary_result = self.binary_inspector.inspect(file_content)

        if binary_result:
            return DetectionResult(
                mime_type=binary_result,
                detected=True,
                detection_method="binary",
            )

        # 2. テキスト形式の判定
        text_result = self.text_inspector.inspect(file_content)

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

