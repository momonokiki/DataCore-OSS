
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MediaInfoResult:
    """MIMEタイプ別Pluginが抽出する技術メタデータ."""

    content_created_at: datetime | None = None
    author_or_device: str | None = None

    width: int | None = None
    height: int | None = None

    latitude: float | None = None
    longitude: float | None = None

    duration_seconds: float | None = None
    sample_rate_hz: int | None = None
    frame_rate: float | None = None

    page_count: int | None = None
    line_count: int | None = None
    encoding: str | None = None

    raw_metadata: dict[str, Any] = field(default_factory=dict)


class BaseMediaInfoPlugin(ABC):
    """MIMEタイプ固有のメタデータ抽出Plugin."""

    @property
    @abstractmethod
    def tool_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def supported_mimetypes(self) -> list[str]:
        raise NotImplementedError

    @property
    def tool_version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Media metadata extraction plugin"

    @abstractmethod
    def extract_from_memory(
        self,
        file_content: bytes,
        mime_type: str,
    ) -> MediaInfoResult:
        raise NotImplementedError

