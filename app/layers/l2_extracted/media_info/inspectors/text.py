import csv
import io
import logging
import xml.etree.ElementTree as ET

from app.layers.l2_extracted.media_info.inspectors.base import (
    BaseInspector,
    InspectionResult,
)

logger = logging.getLogger(__name__)


class TextInspector(BaseInspector):
    """テキスト構造によるファイル形式の識別."""

    MAX_SAMPLE_SIZE = 64 * 1024

    TEXT_ENCODINGS = (
        "utf-8-sig",
        "cp932",
    )

    CSV_DELIMITERS = ",;\t|"

    MIN_CSV_COLUMNS = 2
    MIN_CSV_ROWS = 2

    GPX_NAMESPACES = {
        "http://www.topografix.com/GPX/1/0",
        "http://www.topografix.com/GPX/1/1",
    }

    def inspect(
        self,
        file_content: bytes,
        extension: str | None = None,
    ) -> InspectionResult | None:
        if not file_content:
            return None

        text = self._decode_text(file_content)

        if text is None:
            return None

        # バイナリ混入の可能性が高いデータは対象外
        if "\x00" in text:
            return None

        # XMLを先に判定
        if self._is_xml(text):
            format_type = self._detect_xml_format(text)

            return self._log_detection(
                "application/xml",
                format_type,
            )

        # CSVを判定
        if self._is_csv(text, extension):
            return self._log_detection(
                "text/csv",
                "csv",
            )

        return None

    def _decode_text(self, file_content: bytes) -> str | None:
        for encoding in self.TEXT_ENCODINGS:
            try:
                return file_content.decode(encoding)
            except UnicodeDecodeError:
                continue

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

    def _detect_xml_format(self, text: str) -> str:
        """
        XMLのルート要素から形式を識別する。

        GPXはルート要素名とnamespaceの両方を確認する。
        それ以外のXMLは一般形式として扱う。
        """

        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return "xml"

        if not root.tag.startswith("{"):
            return "xml"

        namespace, _, local_name = root.tag[1:].partition("}")

        if (
            local_name == "gpx"
            and namespace in self.GPX_NAMESPACES
        ):
            return "gpx"

        return "xml"

    def _is_csv(
        self,
        text: str,
        extension: str | None = None,
    ) -> bool:
        sample = text[:self.MAX_SAMPLE_SIZE]

        # CSV拡張子がある場合は帳票ヘッダー等を許容する
        if extension == ".csv":
            return self._is_csv_with_header(sample)

        # 拡張子がない場合は従来に近い厳格な判定
        return self._is_strict_csv(sample)

    def _is_strict_csv(self, sample: str) -> bool:
        try:
            dialect = csv.Sniffer().sniff(
                sample,
                delimiters=self.CSV_DELIMITERS,
            )

            rows = list(
                csv.reader(
                    io.StringIO(sample),
                    dialect,
                )
            )

            if len(rows) < self.MIN_CSV_ROWS:
                return False

            column_count = len(rows[0])

            if column_count < self.MIN_CSV_COLUMNS:
                return False

            return all(
                len(row) == column_count
                for row in rows[:10]
                if row
            )

        except csv.Error:
            return False

    def _is_csv_with_header(self, sample: str) -> bool:
        """
        CSV拡張子がある場合の緩和判定。

        先頭に帳票情報やヘッダーが存在しても、
        その後に一定数の列構造が揃った行があれば候補とする。
        """

        for delimiter in self.CSV_DELIMITERS:
            try:
                rows = list(
                    csv.reader(
                        io.StringIO(sample),
                        delimiter=delimiter,
                    )
                )
            except csv.Error:
                continue

            if self._has_consistent_rows(rows):
                return True

        return False

    def _has_consistent_rows(self, rows: list[list[str]]) -> bool:
        """
        連続する行の列数が一致する領域を探す。

        空行は判定から除外する。
        """

        consecutive_count = 0
        previous_column_count = None

        for row in rows:
            if not row or not any(cell.strip() for cell in row):
                continue

            column_count = len(row)

            if column_count < self.MIN_CSV_COLUMNS:
                consecutive_count = 0
                previous_column_count = None
                continue

            if column_count == previous_column_count:
                consecutive_count += 1
            else:
                consecutive_count = 1
                previous_column_count = column_count

            if consecutive_count >= self.MIN_CSV_ROWS:
                return True

        return False

    @staticmethod
    def _log_detection(
        mime_type: str,
        format_type: str,
    ) -> InspectionResult:
        logger.debug(
            "Text format detected: mime_type=%s, format_type=%s",
            mime_type,
            format_type,
        )

        return InspectionResult(
            mime_type=mime_type,
            format_type=format_type,
        )
