#!/usr/bin/env python3
"""Publish a generated CDR CSV as signed, governed Kafka stream chunks."""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from aiokafka import AIOKafkaProducer

from kozmik_executor.ingestion.models import StreamIngestionChunk
from kozmik_executor.messaging_security import wrap_message

NAMESPACE = UUID("53f530cb-acde-42f2-bbe4-8dbe48533696")


async def publish(arguments) -> tuple[UUID, int, int]:
    stream_id = uuid4()
    producer = AIOKafkaProducer(
        bootstrap_servers=arguments.bootstrap_servers,
        enable_idempotence=True,
        acks="all",
        max_request_size=5 * 1024 * 1024,
        request_timeout_ms=10_000,
    )
    chunks = 0
    rows = 0
    try:
        await asyncio.wait_for(producer.start(), timeout=15)
    except TimeoutError as error:
        raise RuntimeError(
            f"Kafka is not reachable at {arguments.bootstrap_servers}. "
            "Start the infrastructure with ./start-all.sh and retry."
        ) from error
    try:
        with arguments.csv.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            batch: list[dict[str, str]] = []
            for record in reader:
                batch.append(record)
                if len(batch) == arguments.chunk_size:
                    await send_chunk(producer, arguments, stream_id, chunks, batch)
                    rows += len(batch)
                    chunks += 1
                    batch = []
            if batch:
                await send_chunk(producer, arguments, stream_id, chunks, batch)
                rows += len(batch)
                chunks += 1
    finally:
        await producer.stop()
    return stream_id, chunks, rows


async def send_chunk(producer, arguments, stream_id, sequence, records) -> None:
    entity = {
        "id": str(arguments.entity_id),
        "name": arguments.csv.stem,
        "description": None,
        "columns": [
            {"columnName": "cdr_id", "businessName": "CDR ID", "dataType": "STRING",
             "ordinalPosition": 1},
            {"columnName": "event_time", "businessName": "Event time",
             "dataType": "TIMESTAMP", "ordinalPosition": 2},
            {"columnName": "origin_region", "businessName": "Origin region",
             "dataType": "STRING", "ordinalPosition": 3},
            {"columnName": "destination_region", "businessName": "Destination region",
             "dataType": "STRING", "ordinalPosition": 4},
            {"columnName": "duration_seconds", "businessName": "Duration seconds",
             "dataType": "INTEGER", "ordinalPosition": 5},
            {"columnName": "call_type", "businessName": "Call type", "dataType": "STRING",
             "ordinalPosition": 6},
            {"columnName": "roaming", "businessName": "Roaming", "dataType": "BOOLEAN",
             "ordinalPosition": 7},
            {"columnName": "charge_amount", "businessName": "Charge amount",
             "dataType": "DECIMAL", "ordinalPosition": 8},
        ],
    }
    chunk = StreamIngestionChunk(
        chunkId=uuid5(NAMESPACE, f"{stream_id}:{sequence}"),
        streamId=stream_id, entity=entity,
        sourceId=arguments.source_id,
        producedAt=datetime.now(timezone.utc),
        sequence=sequence,
        records=records,
    )
    await asyncio.wait_for(
        producer.send_and_wait(
            arguments.topic,
            wrap_message(chunk.model_dump_json(by_alias=True).encode()),
            key=str(arguments.entity_id).encode(),
        ),
        timeout=30,
    )
    if sequence == 0 or (sequence + 1) % 10 == 0:
        print(f"Published CDR chunk {sequence + 1}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--entity-id", type=UUID, required=True)
    parser.add_argument("--source-id", default="demo-gsm-towers")
    parser.add_argument("--bootstrap-servers", default="localhost:9092")
    parser.add_argument("--topic", default="ingestion.records.v1")
    parser.add_argument("--chunk-size", type=int, default=5000)
    arguments = parser.parse_args()
    if not 1 <= arguments.chunk_size <= 5000:
        parser.error("chunk-size must be between 1 and 5000")
    stream_id, chunks, rows = asyncio.run(publish(arguments))
    print(f"CDR_STREAM_ID={stream_id}")
    print(f"CDR_CHUNKS={chunks}")
    print(f"CDR_ROWS={rows}")


if __name__ == "__main__":
    main()
