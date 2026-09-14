"""MQTT -> Kafka bridge: the fan-in from the device bus to the processing backbone.

Subscribes to the MQTT topic tree and republishes each message to Kafka, keyed by sensor id so
a sensor's readings land on one partition (preserving per-sensor order). Messages are forwarded
verbatim: the poller already produced the canonical event, so the bridge only moves bytes and
sets the key.

Usage:
    python -m sensor_reliability.bridge
"""

from __future__ import annotations

import json
import signal

import paho.mqtt.client as mqtt
from confluent_kafka import Producer

from .config import Config


def _kafka_key(payload: bytes) -> str | None:
    try:
        return str(json.loads(payload)["sensor_id"])
    except (ValueError, KeyError, TypeError):
        return None  # unkeyed; Kafka will assign a partition round-robin


def run(cfg: Config | None = None) -> None:
    cfg = cfg or Config.from_env()
    producer = Producer({"bootstrap.servers": cfg.kafka_bootstrap})

    def on_connect(client, userdata, flags, reason_code, properties):
        client.subscribe(f"{cfg.mqtt_topic_prefix}/#", qos=1)
        print(f"subscribed to {cfg.mqtt_topic_prefix}/# ; producing to {cfg.kafka_topic}")

    def on_message(client, userdata, msg):
        producer.produce(cfg.kafka_topic, key=_kafka_key(msg.payload), value=msg.payload)
        producer.poll(0)  # serve delivery callbacks without blocking

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sc-bridge")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(cfg.mqtt_host, cfg.mqtt_port)

    def _shutdown(*_):
        client.disconnect()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        client.loop_forever()
    finally:
        producer.flush()


if __name__ == "__main__":
    run()
