import logging

from app.layers.l2_extracted.media_info.inspectors.base import (
    BaseInspector,
)

logger = logging.getLogger(__name__)


class BinaryInspector(BaseInspector):
    """マジックバイトによるバイナリ形式の識別."""

    SIGNATURES = (
        (b"\xFF\xD8\xFF", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"%PDF-", "application/pdf"),
        (b"ID3", "audio/mpeg"),
        (b"fLaC", "audio/flac"),
        (b"OggS", "application/ogg"),
        (b"\x1A\x45\xDF\xA3", "video/x-matroska"),
        (b"PK\x03\x04", "application/zip"),
    )

    RIFF_TYPES = {
        b"WEBP": "image/webp",
        b"WAVE": "audio/wav",
        b"AVI ": "video/x-msvideo",
    }

    MP4_BRANDS = {
        b"isom",
        b"iso2",
        b"iso3",
        b"iso4",
        b"iso5",
        b"iso6",
        b"mp41",
        b"mp42",
        b"avc1",
        b"M4V ",
        b"M4VH",
        b"M4VP",
    }

    def inspect(
        self,
        file_content: bytes,
        extension: str | None = None,
    ) -> str | None:
        if not file_content:
            return None

        # 1. ISO Base Media File Format（MP4 / QuickTime）
        mime_type = self._detect_iso_bmff(file_content)

        if mime_type:
            return self._log_detection(mime_type)

        # 2. RIFFコンテナ（WebP / WAV / AVI）
        mime_type = self._detect_riff(file_content)

        if mime_type:
            return self._log_detection(mime_type)

        # 3. その他のマジックバイト
        for signature, mime_type in self.SIGNATURES:
            if file_content.startswith(signature):
                return self._log_detection(mime_type)

        return None

    def _detect_iso_bmff(self, file_content: bytes) -> str | None:
        if len(file_content) < 12:
            return None

        if file_content[4:8] != b"ftyp":
            return None

        brand = file_content[8:12]

        if brand == b"qt  ":
            return "video/quicktime"

        if brand in self.MP4_BRANDS:
            return "video/mp4"

        logger.debug(
            "Unsupported ISO BMFF brand: %s",
            brand.decode("ascii", errors="replace"),
        )

        return None

    def _detect_riff(self, file_content: bytes) -> str | None:
        if len(file_content) < 12:
            return None

        if file_content[:4] != b"RIFF":
            return None

        riff_type = file_content[8:12]
        return self.RIFF_TYPES.get(riff_type)

    @staticmethod
    def _log_detection(mime_type: str) -> str:
        logger.debug(
            "Binary format detected: %s",
            mime_type,
        )
        return mime_type
