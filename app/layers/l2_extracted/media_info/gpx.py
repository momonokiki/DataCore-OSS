# app/layers/l2_extracted/media_info/gpx.py
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

from app.layers.l2_extracted.media_info.base import BaseMediaInfoPlugin, MediaInfoResult

logger = logging.getLogger(__name__)

_GPX_NAMESPACES = {
    "http://www.topografix.com/GPX/1/0",
    "http://www.topografix.com/GPX/1/1",
}

_POINT_TAGS = ("trkpt", "rtept", "wpt")


def _local_name(tag: str) -> str:
    """'{namespace}trkpt' -> 'trkpt' のようにローカル名だけを取り出す。"""
    return tag.rsplit("}", 1)[-1]


def _namespace_of(tag: str) -> Optional[str]:
    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return None


def _parse_time(text: Optional[str]) -> Optional[datetime]:
    """GPX の <time>（ISO 8601、末尾 Z あり）を datetime にする。失敗したら None。"""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_coord(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class GpxPlugin(BaseMediaInfoPlugin):
    """
    GPXファイルから要約メタデータを抽出するL2プラグイン。

    L2には軌跡そのものは入れない（軌跡はL3で扱う）。
    ここで取るのは、始点の座標・時刻と、件数や時刻範囲などの要約だけ。
    """

    @property
    def tool_name(self) -> str:
        return "gpx_extractor"

    @property
    def supported_mimetypes(self) -> list[str]:
        # GPXのMIMEは一般XMLと同じ application/xml。
        # 区別はMIMEではなく、検出器の format_type と本プラグイン内の再検証で行う。
        return ["application/xml"]

    def extract_from_memory(self, file_content: bytes, mime_type: str) -> MediaInfoResult:
        if mime_type not in self.supported_mimetypes:
            raise ValueError(f"Unsupported MIME type in {self.tool_name}: {mime_type}")

        try:
            root = ET.fromstring(file_content)
        except ET.ParseError as exc:
            logger.error(f"[{self.tool_name}] Failed to parse XML binary: {exc}", exc_info=True)
            raise ValueError("生バイナリからXMLへのパースに失敗しました。") from exc

        # MIMEだけではGPXと一般XMLを区別できないので、ルート要素とnamespaceを再検証する
        if _local_name(root.tag) != "gpx" or _namespace_of(root.tag) not in _GPX_NAMESPACES:
            raise ValueError(f"Not a GPX document in {self.tool_name}: root={root.tag}")

        track_count = 0
        route_count = 0
        waypoint_count = 0
        track_point_count = 0
        route_point_count = 0

        # 種別ごとの最初の点（始点候補）と、全点の時刻範囲
        first_point_by_tag: dict[str, tuple[Optional[float], Optional[float], Optional[datetime]]] = {}
        min_time: Optional[datetime] = None
        max_time: Optional[datetime] = None

        for elem in root.iter():
            name = _local_name(elem.tag)

            if name == "trk":
                track_count += 1
            elif name == "rte":
                route_count += 1
            elif name in _POINT_TAGS:
                if name == "trkpt":
                    track_point_count += 1
                elif name == "rtept":
                    route_point_count += 1
                else:
                    waypoint_count += 1

                lat = _parse_coord(elem.get("lat"))
                lon = _parse_coord(elem.get("lon"))
                if lat is not None and not (-90.0 <= lat <= 90.0):
                    lat = None
                if lon is not None and not (-180.0 <= lon <= 180.0):
                    lon = None

                point_time: Optional[datetime] = None
                for child in elem:
                    if _local_name(child.tag) == "time":
                        point_time = _parse_time(child.text)
                        break

                if name not in first_point_by_tag:
                    first_point_by_tag[name] = (lat, lon, point_time)

                if point_time is not None:
                    if min_time is None or point_time < min_time:
                        min_time = point_time
                    if max_time is None or point_time > max_time:
                        max_time = point_time

        # 始点は trkpt 優先、なければ rtept、それもなければ wpt
        start_lat: Optional[float] = None
        start_lon: Optional[float] = None
        start_time: Optional[datetime] = None
        for tag in _POINT_TAGS:
            if tag in first_point_by_tag:
                start_lat, start_lon, start_time = first_point_by_tag[tag]
                break

        creator = root.get("creator")
        version = root.get("version")

        result = MediaInfoResult(
            content_created_at=start_time if start_time is not None else min_time,
            author_or_device=creator,
            latitude=start_lat,
            longitude=start_lon,
            raw_metadata={
                "creator": creator,
                "gpx_version": version,
                "track_count": track_count,
                "route_count": route_count,
                "waypoint_count": waypoint_count,
                "track_point_count": track_point_count,
                "route_point_count": route_point_count,
                "total_point_count": track_point_count + route_point_count + waypoint_count,
                "start_time": min_time.isoformat() if min_time else None,
                "end_time": max_time.isoformat() if max_time else None,
            },
        )
        return result