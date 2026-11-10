# app/layers/l2_extracted/media_info/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
from datetime import datetime


@dataclass
class MediaInfoResult:
    content_created_at: Optional[datetime] = None
    author_or_device: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    raw_metadata: Optional[dict[str, Any]] = None


class BaseMediaInfoPlugin(ABC):
    @property
    @abstractmethod
    def tool_name(self) -> str: pass

    @property
    @abstractmethod
    def supported_mimetypes(self) -> list[str]: pass

    @abstractmethod
    def extract_from_memory(self, file_content: bytes, mime_type: str) -> MediaInfoResult: pass
