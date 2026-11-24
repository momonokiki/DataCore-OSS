from abc import ABC, abstractmethod


class BaseInspector(ABC):
    """ファイル形式を識別する共通Inspector."""

    @abstractmethod
    def inspect(
        self,
        file_content: bytes,
        extension: str | None = None,
    ) -> str | None:
        raise NotImplementedError
