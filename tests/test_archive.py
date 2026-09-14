import datetime as dt

from sensor_reliability.archive import parse_csv

FETCHED_AT = dt.datetime(2026, 9, 12, 9, 0, tzinfo=dt.timezone.utc)

# Real header layouts (see the archive; columns vary by sensor type).
SDS011_CSV = (
    "sensor_id;sensor_type;location;lat;lon;timestamp;P1;durP1;ratioP1;P2;durP2;ratioP2\n"
    "18818;SDS011;9537;45.594;9.294;2026-09-11T00:01:06;3.83;;;0.63;;\n"
)
BME280_CSV = (
    "sensor_id;sensor_type;location;lat;lon;timestamp;pressure;altitude;pressure_sealevel;"
    "temperature;humidity\n"
    "18819;BME280;9537;45.594;9.294;2026-09-11T00:01:06;99490.31;;;21.23;91.09\n"
)


def test_parse_sds011_keeps_pm_only():
    (ev,) = parse_csv(SDS011_CSV, FETCHED_AT)
    assert ev["source"] == "archive"
    assert ev["record_id"] is None
    assert ev["sensor_id"] == 18818
    assert ev["location_id"] == 9537
    assert ev["indoor"] == 0  # stamped: study population is outdoor by construction
    assert ev["timestamp"] == "2026-09-11T00:01:06Z"  # naive ISO -> Z appended
    assert ev["values"] == {"P1": 3.83, "P2": 0.63}  # durP1/ratioP1/... dropped


def test_parse_bme280_keeps_climate_only():
    (ev,) = parse_csv(BME280_CSV, FETCHED_AT)
    assert ev["values"] == {"pressure": 99490.31, "temperature": 21.23, "humidity": 91.09}
    assert "altitude" not in ev["values"]
    assert "pressure_sealevel" not in ev["values"]


def test_parse_skips_blank_lines_and_header_only():
    assert parse_csv("sensor_id;sensor_type;location;lat;lon;timestamp;P1\n", FETCHED_AT) == []
