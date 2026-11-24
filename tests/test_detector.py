import pytest

from app.layers.l2_extracted.media_info.detector import (
    MediaTypeDetector,
)


@pytest.fixture
def detector():
    return MediaTypeDetector()


@pytest.mark.parametrize(
    ("content", "expected_mime", "expected_format"),
    [
        (
            b"\xff\xd8\xff\xe0\x00\x10JFIF",
            "image/jpeg",
            "jpeg",
        ),
        (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            "image/png",
            "png",
        ),
        (
            b"%PDF-1.7\n",
            "application/pdf",
            "pdf",
        ),
    ],
)
def test_binary_formats(
    detector,
    content,
    expected_mime,
    expected_format,
):
    result = detector.detect(content)

    assert result.detected is True
    assert result.mime_type == expected_mime
    assert result.format_type == expected_format
    assert result.detection_method == "binary"


def test_csv_utf8(detector):
    content = (
        "日付,店舗,金額\n"
        "2026-11-01,店舗A,1200\n"
        "2026-11-02,店舗B,2300\n"
    ).encode("utf-8")

    result = detector.detect(content, "sample.csv")

    assert result.detected is True
    assert result.mime_type == "text/csv"
    assert result.format_type == "csv"
    assert result.detection_method == "text"


def test_csv_cp932(detector):
    content = (
        "日付,店舗,金額\n"
        "2026-11-01,店舗A,1200\n"
        "2026-11-02,店舗B,2300\n"
    ).encode("cp932")

    result = detector.detect(content, "sample.csv")

    assert result.detected is True
    assert result.mime_type == "text/csv"
    assert result.format_type == "csv"


def test_general_xml(detector):
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
<root>
    <item>example</item>
</root>
"""

    result = detector.detect(content, "sample.xml")

    assert result.detected is True
    assert result.mime_type == "application/xml"
    assert result.format_type == "xml"
    assert result.detection_method == "text"


@pytest.mark.parametrize(
    "namespace",
    [
        "http://www.topografix.com/GPX/1/0",
        "http://www.topografix.com/GPX/1/1",
    ],
)
def test_gpx(namespace, detector):
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="DataCore"
     xmlns="{namespace}">
    <trk>
        <name>Test Track</name>
    </trk>
</gpx>
""".encode("utf-8")

    result = detector.detect(content, "sample.gpx")

    assert result.detected is True
    assert result.mime_type == "application/xml"
    assert result.format_type == "gpx"


def test_xml_without_gpx_namespace_is_general_xml(detector):
    content = b"""<?xml version="1.0"?>
<gpx>
    <trk />
</gpx>
"""

    result = detector.detect(content, "sample.xml")

    assert result.detected is True
    assert result.mime_type == "application/xml"
    assert result.format_type == "xml"


def test_unknown_format(detector):
    content = b"\x00\x01\x02\x03\x04"

    result = detector.detect(content)

    assert result.detected is False
    assert result.mime_type == "application/octet-stream"
    assert result.format_type is None
    assert result.detection_method == "none"


def test_empty_content(detector):
    result = detector.detect(b"")

    assert result.detected is False
    assert result.mime_type == "application/octet-stream"
    assert result.format_type is None
    assert result.detection_method == "none"


def test_content_takes_priority_over_extension(detector):
    content = b"\xff\xd8\xff\xe0\x00\x10JFIF"

    result = detector.detect(content, "sample.png")

    assert result.detected is True
    assert result.mime_type == "image/jpeg"
    assert result.format_type == "jpeg"
