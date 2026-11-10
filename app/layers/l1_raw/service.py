"""
L1層のファイルインジェスション処理
ユーザーがアップロードしたファイルを CAS で管理し、L1テーブルに登録する処理
"""
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.layers.l1_raw.models import L1File, L1FileUpload
from app.infrastructure.storage import StorageAdapter, calculate_file_hash


class L1FileIngestionService:
    """L1層のファイル取り込みサービス"""

    def __init__(self, storage_adapter: StorageAdapter):
        self.storage = storage_adapter

    async def ingest_files(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        files: List[tuple[str, bytes]],  # [(filename, content), ...]
    ) -> List[tuple[str, str, Optional[str]]]:
        """
        複数のファイルを一括登録し、アップロード履歴を作成

        Args:
            session: DB session
            user_id: アップロードするユーザーID
            files: [(filename, content), ...] のリスト

        Returns:
            [(filename, file_hash, storage_path), ...] のリスト
        """
        results = []

        for filename, content in files:
            try:
                # 1. ハッシュ計算
                file_hash = calculate_file_hash(content)
                mime_type = self._guess_mime_type(filename)
                file_size_bytes = len(content)

                # 2. ストレージに保存（既に存在する場合はスキップ）
                storage_path = await self.storage.save(file_hash, content)

                # 3. L1File を登録（既に存在する場合は重複チェック）
                existing_l1 = await session.execute(
                    select(L1File).where(L1File.file_hash == file_hash)
                )
                l1_file = existing_l1.scalars().first()

                if not l1_file:
                    l1_file = L1File(
                        file_hash=file_hash,
                        mime_type=mime_type,
                        file_size_bytes=file_size_bytes,
                        storage_path=storage_path,
                    )
                    session.add(l1_file)
                    await session.flush()

                # 4. L1FileUpload を登録（アップロード履歴）
                l1_upload = L1FileUpload(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    file_hash=file_hash,
                    original_filename=filename,
                )
                session.add(l1_upload)
                await session.flush()

                results.append((filename, file_hash, storage_path))

            except Exception as e:
                # 個別ファイルのエラーをログして続行
                print(f"Failed to ingest {filename}: {e}")
                results.append((filename, "", None))

        await session.commit()
        return results

    @staticmethod
    def _guess_mime_type(filename: str) -> str:
        """ファイル拡張子からMIMEタイプを推定"""
        import mimetypes

        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"
