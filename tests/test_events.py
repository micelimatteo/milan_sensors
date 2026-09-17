import datetime as dt

from sensor_reliability.events import record_to_event

FETCHED_AT = dt.datetime(2026, 9, 12, 9, 0, tzinfo=dt.UTC)

RECORD = {
    "id": 30675246373,
    "timestamp": "2026-09-12 09:21:51",
    "location": {"id": 45825, "latitude": "45.434", "longitude": "9.116",
                 "country": "IT", "indoor": 0, "exact_location": 0},
    "sensor": {"id": 59971, "sensor_type": {"name": "BME280"}},
    "sensordatavalues": [
        {"value_type": "temperature", "value": "24.02"},
        {"value_type": "humidity", "value": "100.00"},
        {"value_type": "pressure_at_sealevel", "value": 102313.83},  # not in the wire contract
    ],
}


def test_record_to_event_shape_and_time():
    ev = record_to_event(RECORD, FETCHED_AT)
    assert ev["schema"] == "sc.reading.v1"
    assert ev["source"] == "live"
    assert ev["sensor_id"] == 59971
    assert ev["location_id"] == 45825
    assert ev["indoor"] == 0
    assert ev["timestamp"] == "2026-09-12T09:21:51Z"  # space -> T, Z appended
    assert ev["fetched_at"] == "2026-09-12T09:00:00Z"


def test_values_map_filters_to_wire_contract():
    ev = record_to_event(RECORD, FETCHED_AT)
    assert ev["values"] == {"temperature": 24.02, "humidity": 100.0}
    assert "pressure_at_sealevel" not in ev["values"]


def test_record_without_sensor_id_is_dropped():
    assert record_to_event({"sensor": {}, "sensordatavalues": []}, FETCHED_AT) is None
