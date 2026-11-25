# app/layers/l3_structured/addons/gpx_stay/detector.py
"""
GPXのトラックポイントから「滞在」を検出する確定的なロジック。

L3には軌跡そのものは保存しない。ある場所に一定時間とどまった区間を
滞在として切り出し、その重心と滞在時間だけを返す。
"""

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# ============================================================
# 滞在検出パラメータ（調整はここ）
# ============================================================
DISTANCE_THRESHOLD_M = 100.0  # 重心からこの距離以内は「同じ場所」とみなす
MIN_STAY_MINUTES = 3          # これ未満の滞留は滞在とみなさない（ドライブスルー検出のため短め。信号待ちも拾いうる）
MAX_GAP_MINUTES = 30          # 点がこれ以上空いたら滞在をそこで分ける

_GPX_NAMESPACES = {
    "http://www.topografix.com/GPX/1/0",
    "http://www.topografix.com/GPX/1/1",
}

_EARTH_RADIUS_M = 6371000.0


@dataclass
class TrackPoint:
    latitude: float
    longitude: float
    time: datetime


@dataclass
class Stay:
    latitude: float   # 重心
    longitude: float  # 重心
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    point_count: int
    max_distance_m: float  # 重心から最も離れた所属点までの距離


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace_of(tag: str) -> Optional[str]:
    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return None


def _parse_time(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間の距離（メートル）。"""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def extract_track_points(file_bytes: bytes) -> list[TrackPoint]:
    """
    GPXバイト列から trkpt を取り出し、時刻順に並べて返す。
    座標または時刻のない点は、滞在判定に使えないため除外する。
    GPXでない場合は ValueError。
    """
    try:
        root = ET.fromstring(file_bytes)
    except ET.ParseError as exc:
        raise ValueError("生バイナリからXMLへのパースに失敗しました。") from exc

    if _local_name(root.tag) != "gpx" or _namespace_of(root.tag) not in _GPX_NAMESPACES:
        raise ValueError(f"Not a GPX document: root={root.tag}")

    points: list[TrackPoint] = []
    for elem in root.iter():
        if _local_name(elem.tag) != "trkpt":
            continue
        try:
            lat = float(elem.get("lat"))
            lon = float(elem.get("lon"))
        except (TypeError, ValueError):
            continue
        point_time: Optional[datetime] = None
        for child in elem:
            if _local_name(child.tag) == "time":
                point_time = _parse_time(child.text)
                break
        if point_time is None:
            continue
        points.append(TrackPoint(latitude=lat, longitude=lon, time=point_time))

    points.sort(key=lambda p: p.time)
    return points


def detect_stays(
    points: list[TrackPoint],
    distance_threshold_m: float = DISTANCE_THRESHOLD_M,
    min_stay_minutes: float = MIN_STAY_MINUTES,
    max_gap_minutes: float = MAX_GAP_MINUTES,
) -> list[Stay]:
    """
    点列から滞在を切り出す。

    - 点が現在の重心から distance_threshold_m 以内なら同じ滞在に取り込む
    - 重心から外れるか、点の間隔が max_gap_minutes を超えたら滞在を閉じる
    - 閉じた滞在の持続時間が min_stay_minutes 未満なら捨てる
    """
    min_duration_s = min_stay_minutes * 60
    max_gap_s = max_gap_minutes * 60

    stays: list[Stay] = []
    cluster: list[TrackPoint] = []
    sum_lat = 0.0
    sum_lon = 0.0

    def close_cluster() -> None:
        if not cluster:
            return
        started = cluster[0].time
        ended = cluster[-1].time
        duration_s = int((ended - started).total_seconds())
        if duration_s >= min_duration_s:
            c_lat = sum_lat / len(cluster)
            c_lon = sum_lon / len(cluster)
            max_dist = max(
                haversine_m(c_lat, c_lon, p.latitude, p.longitude) for p in cluster
            )
            stays.append(
                Stay(
                    latitude=c_lat,
                    longitude=c_lon,
                    started_at=started,
                    ended_at=ended,
                    duration_seconds=duration_s,
                    point_count=len(cluster),
                    max_distance_m=max_dist,
                )
            )

    for point in points:
        if cluster:
            gap_s = (point.time - cluster[-1].time).total_seconds()
            c_lat = sum_lat / len(cluster)
            c_lon = sum_lon / len(cluster)
            dist_m = haversine_m(c_lat, c_lon, point.latitude, point.longitude)
            if gap_s > max_gap_s or dist_m > distance_threshold_m:
                close_cluster()
                cluster = []
                sum_lat = 0.0
                sum_lon = 0.0
        cluster.append(point)
        sum_lat += point.latitude
        sum_lon += point.longitude

    close_cluster()
    return stays
