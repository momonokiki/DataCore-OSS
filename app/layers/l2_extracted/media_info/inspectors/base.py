from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class InspectionResult:
    """Inspectorによるファイル形式の識別結果."""

    mime_type: str
    format_type: str


class BaseInspector(ABC):
    """ファイル形式を識別する共通Inspector."""

    @abstractmethod
    def inspect(
        self,
        file_content: bytes,
        extension: str | None = None,
    ) -> InspectionResult | None:
        raise NotImplementedError
