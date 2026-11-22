import csv
import io
import logging
import xml.etree.ElementTree as ET

from app.layers.l2_extracted.media_info.inspectors.base import (
    BaseInspector,
)

logger = logging.getLogger(__name__)


class TextInspector(BaseInspector):
    """テキスト構造によるファイル形式の識別."""

    MAX_SAMPLE_SIZE = 64 * 1024

    def inspect(self, file_content: bytes) -> str | None:
        if not file_content:
            return None

        # UTF-8 BOMを考慮してデコード
        try:
            text = file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None

        # バイナリ混入の可能性が高いデータは対象外
        if "\x00" in text:
            return None

        # XMLを先に判定
        if self._is_xml(text):
            return self._log_detection("application/xml")

        # CSVを判定
        if self._is_csv(text):
            return self._log_detection("text/csv")

        return None

    def _is_xml(self, text: str) -> bool:
        sample = text[:self.MAX_SAMPLE_SIZE].lstrip()

        if not sample.startswith("<"):
            return False

        try:
            ET.fromstring(text)
            return True
        except ET.ParseError:
            return False

    def _is_csv(self, text: str) -> bool:
        sample = text[:self.MAX_SAMPLE_SIZE]

        try:
            dialect = csv.Sniffer().sniff(
                sample,
                delimiters=",;\t|",
            )

            rows = list(
                csv.reader(
                    io.StringIO(sample),
                    dialect,
            )
            )

            if len(rows) < 2:
                return False

            column_count = len(rows[0])

            if column_count < 2:
                return False

            return all(
                len(row) == column_count
                for row in rows[:10]
                if row
            )

        except csv.Error:
            return False

    @staticmethod
    def _log_detection(mime_type: str) -> str:
        logger.debug(
            "Text format detected: %s",
            mime_type,
        )
        return mime_type
