# app/layers/l2_extracted/media_info/image_exif.py
import io
import logging
import math
from datetime import datetime
from typing import Any, Optional

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from app.layers.l2_extracted.media_info.base import BaseMediaInfoPlugin, MediaInfoResult

logger = logging.getLogger(__name__)


class ImageExifPlugin(BaseMediaInfoPlugin):
    """
    画像ファイルから物理属性（幅・高さ）および
    EXIFメタデータ（撮影日時、デバイス名、GPS座標）を抽出する本番用L2プラグイン。
    """

    @property
    def tool_name(self) -> str:
        return "image_exif_extractor"

    @property
    def supported_mimetypes(self) -> list[str]:
        return ["image/jpeg", "image/png", "image/webp"]
    
    def _sanitize_for_json(self, obj: Any) -> Any:
        NUL = chr(0)  # 💡  の代わりに chr(0)
        if isinstance(obj, dict):
            return {str(k): self._sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._sanitize_for_json(x) for x in obj]
        elif isinstance(obj, bytes):
            decoded = obj.decode("utf-8", errors="replace")
            return decoded.replace(NUL, "")
        elif isinstance(obj, str):
            return obj.replace(NUL, "")
        elif isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        elif isinstance(obj, (int, bool)) or obj is None:
            return obj
        else:
            try:
                converted = float(obj)
                if math.isnan(converted) or math.isinf(converted):
                    return None
                return converted
            except (TypeError, ValueError):
                try:
                    return str(obj).replace(NUL, "")
                except Exception:
                    return None


    def extract_from_memory(self, file_content: bytes, mime_type: str) -> MediaInfoResult:
        if mime_type not in self.supported_mimetypes:
            raise ValueError(f"Unsupported MIME type in {self.tool_name}: {mime_type}")

        try:
            img = Image.open(io.BytesIO(file_content))
            width, height = img.size
        except Exception as exc:
            logger.error(f"[{self.tool_name}] Failed to open image binary: {exc}", exc_info=True)
            raise ValueError("生バイナリから画像へのデコードに失敗しました。") from exc

        result = MediaInfoResult(
            width=width,
            height=height,
            raw_metadata={}
        )

        try:
            exif_data = img._getexif()
            if not exif_data:
                return result

            readable_exif: dict[str, Any] = {}
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                readable_exif[tag_name] = value

            # 3. 日時のパース
            date_str = readable_exif.get("DateTimeOriginal") or readable_exif.get("DateTime")
            if date_str and isinstance(date_str, str):
                try:
                    result.content_created_at = datetime.strptime(
                        date_str.strip().replace("", ""),
                        "%Y:%m:%d %H:%M:%S"
                    )
                except ValueError:
                    pass

            # 4. デバイス名
            make = readable_exif.get("Make")
            model = readable_exif.get("Model")
            device_parts = [str(p).strip().replace("", "") for p in (make, model) if p]
            if device_parts:
                result.author_or_device = " ".join(device_parts).strip()

            # 5. GPS位置情報の安全なパース
            gps_info = exif_data.get(34853)
            if gps_info and isinstance(gps_info, dict):
                readable_gps = {}
                for g_id, g_val in gps_info.items():
                    g_name = GPSTAGS.get(g_id, str(g_id))
                    readable_gps[g_name] = g_val

                readable_exif["GPSInfo"] = readable_gps

                lat, lon = self._parse_gps_coords(readable_gps)

                # 💡【NaN 防御】GPS座標が NaN になった場合は None に置換
                if lat is not None and math.isnan(lat):
                    lat = None
                if lon is not None and math.isnan(lon):
                    lon = None

                result.latitude = lat
                result.longitude = lon

            # 💡 最後に raw_metadata 全体を、JSONBで爆発しないように完全にクレンジングする
            result.raw_metadata = self._sanitize_for_json(readable_exif)

        except Exception as e:
            logger.error(f"[{self.tool_name}] Error parsing EXIF/GPS metadata: {e}", exc_info=True)

        return result

    @staticmethod
    def _parse_gps_coords(gps_info: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
        def _to_decimal(rational_triplet: Any, ref: Optional[str]) -> Optional[float]:
            if not rational_triplet or len(rational_triplet) < 3:
                return None
            try:
                d = float(rational_triplet[0])
                m = float(rational_triplet[1])
                s = float(rational_triplet[2])

                # 💡【NaN 防御】度分秒のいずれかが NaN の場合は即座に諦める
                if math.isnan(d) or math.isnan(m) or math.isnan(s):
                    return None

                decimal_val = d + (m / 60.0) + (s / 3600.0)

                if ref and str(ref).strip().replace("", "") in ("S", "W"):
                    decimal_val = -decimal_val

                # 最終チェック
                if math.isnan(decimal_val) or math.isinf(decimal_val):
                    return None

                return decimal_val
            except (ValueError, TypeError, ZeroDivisionError, IndexError):
                return None

        return (
            _to_decimal(gps_info.get("GPSLatitude"), gps_info.get("GPSLatitudeRef")),
            _to_decimal(gps_info.get("GPSLongitude"), gps_info.get("GPSLongitudeRef"))
        )
