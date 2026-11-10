
from abc import ABC, abstractmethod
from typing import Any, Dict, List, TypedDict


class OcrPluginResponse(TypedDict):
    """
    OCRプラグインが返却する標準形式。

    Orchestratorがこの形式をL2Artifactへ保存する。
    """

    full_text: str
    words: List[Dict[str, Any]]
    metadata_json: Dict[str, Any]


class BaseOcrPlugin(ABC):
    """
    すべてのL2 OCRプラグインが実装する基底クラス。
    """

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """l2_tools.nameに対応する一意の識別名。"""
        pass

    @property
    @abstractmethod
    def tool_version(self) -> str:
        """プラグインのバージョン。"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """使用するOCRモデル・エンジン名。"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """プラグインの説明。"""
        pass

    @property
    @abstractmethod
    def supported_mimetypes(self) -> List[str]:
        """処理可能なMIMEタイプ。"""
        pass

    @abstractmethod
    def process_from_memory(
        self,
        file_content: bytes,
        mime_type: str,
    ) -> OcrPluginResponse:
        """
        原本バイナリを受け取り、OCRを実行する。

        DBセッションは受け取らず、純粋なbytes処理を行う。
        """
        pass

