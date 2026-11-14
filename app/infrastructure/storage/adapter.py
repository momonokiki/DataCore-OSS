"""
StorageAdapter: Content Addressable Storage の抽象インターフェース
ローカル、S3、暗号化など、複数のストレージ実装に対応
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import hashlib


class StorageAdapter(ABC):
    """ストレージアダプタの抽象基底クラス"""

    @abstractmethod
    async def save(self, file_hash: str, content: bytes) -> str:
        """
        ファイルを保存し、ストレージパスを返す

        Args:
            file_hash: SHA-256ハッシュ値
            content: ファイルコンテンツ

        Returns:
            storage_path: ストレージ内の相対パス
        """
        pass

    @abstractmethod
    async def load(self, file_hash: str) -> Optional[bytes]:
        """
        ファイルを読み込む

        Args:
            file_hash: SHA-256ハッシュ値

        Returns:
            content: ファイルコンテンツ、存在しない場合はNone
        """
        pass

    @abstractmethod
    async def exists(self, file_hash: str) -> bool:
        """
        ファイルが存在するか確認

        Args:
            file_hash: SHA-256ハッシュ値

        Returns:
            bool: 存在するか
        """
        pass

    @abstractmethod
    async def delete(self, file_hash: str) -> bool:
        """
        ファイルを削除

        Args:
            file_hash: SHA-256ハッシュ値

        Returns:
            bool: 削除成功
        """
        pass


class LocalStorageAdapter(StorageAdapter):
    """ローカルファイルシステム実装"""

    def __init__(self, base_path: str = "/app/storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_storage_path(self, file_hash: str) -> Path:
        """ファイルハッシュからストレージパスを生成"""
        # hash���の先頭2文字でサブディレクトリを分割（ディレクトリ数制限用）
        subdir = file_hash[:2]
        return self.base_path / subdir / file_hash

    async def save(self, file_hash: str, content: bytes) -> str:
        """ファイルをローカルストレージに保存"""
        storage_path = self._get_storage_path(file_hash)
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # ファイルがすでに存在する場合、ハッシュが一致するか確認
        if storage_path.exists():
            # CASなので同じhashなら重複扱い（上書きしない）
            return str(storage_path.relative_to(self.base_path))

        # ファイルを保存
        storage_path.write_bytes(content)
        return str(storage_path.relative_to(self.base_path))

    async def load(self, file_hash: str) -> Optional[bytes]:
        """ローカルストレージからファイルを読み込む"""
        storage_path = self._get_storage_path(file_hash)
        if not storage_path.exists():
            return None
        return storage_path.read_bytes()

    async def exists(self, file_hash: str) -> bool:
        """ファイルが存在するか確認"""
        storage_path = self._get_storage_path(file_hash)
        return storage_path.exists()

    async def delete(self, file_hash: str) -> bool:
        """ファイルを削除"""
        storage_path = self._get_storage_path(file_hash)
        if not storage_path.exists():
            return False
        storage_path.unlink()
        return True


def calculate_file_hash(content: bytes) -> str:
    """ファイルコンテンツからSHA-256ハッシュを計算"""
    return hashlib.sha256(content).hexdigest()
