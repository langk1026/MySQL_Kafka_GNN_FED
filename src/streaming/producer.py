import logging
import random
import threading
import time

from confluent_kafka import Producer

from src.detection.generator import TransactionGenerator
from src.streaming.serialization import json_serializer
from src.streaming.topics import TOPIC_TRANSACTIONS

logger = logging.getLogger(__name__)


class SimulatedProducer:
    def __init__(
        self,
        bootstrap_servers: str,
        topic: str = TOPIC_TRANSACTIONS,
        interval_min: float = 0.1,
        interval_max: float = 1.0,
    ):
        self._producer = Producer({"bootstrap.servers": bootstrap_servers})
        self._generator = TransactionGenerator()
        self._topic = topic
        self._interval_min = interval_min
        self._interval_max = interval_max
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="simulated-producer"
        )
        self._thread.start()
        logger.info("SimulatedProducer started on topic '%s'", self._topic)

    def _run(self) -> None:
        while self._running:
            tx = self._generator.generate()
            self._producer.produce(
                self._topic,
                key=tx.user_id.encode("utf-8"),
                value=json_serializer(tx.to_dict()),
                callback=self._delivery_callback,
            )
            self._producer.poll(0)
            time.sleep(random.uniform(self._interval_min, self._interval_max))

    def _delivery_callback(self, err, msg):
        if err:
            logger.error("Delivery failed: %s", err)
        else:
            logger.debug(
                "Delivered to %s [%d] @ %d",
                msg.topic(),
                msg.partition(),
                msg.offset(),
            )

    def stop(self) -> None:
        self._running = False
        self._producer.flush(timeout=5)
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("SimulatedProducer stopped")
