import asyncio
import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from minio import Minio
from pydantic import ValidationError
from pyspark.sql import SparkSession, functions as spark_fn, types as spark_types
from kozmik_executor.spark_runtime import run_spark_operation

from kozmik_executor.ingestion.models import (
    StreamIngestionChunk,
    StreamIngestionStatusEvent,
    IngestionSchema,
)
from kozmik_executor.ingestion.worker import NAMESPACE, SchemaClient, TYPE_REGISTRY
from kozmik_executor.logging_config import (
    reset_correlation_id,
    safe_error_code,
    set_correlation_id,
)
from kozmik_executor.messaging_security import unwrap_message, wrap_message

logger = logging.getLogger(__name__)


class StreamChunkLedger:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS stream_chunk ("
            "chunk_id TEXT PRIMARY KEY, stream_id TEXT NOT NULL, row_count INTEGER NOT NULL,"
            "object_key TEXT NOT NULL, completed_at TEXT NOT NULL)"
        )
        self.connection.commit()

    def completed(self, chunk_id: UUID) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM stream_chunk WHERE chunk_id=?", (str(chunk_id),)
        ).fetchone() is not None

    def complete(self, chunk_id: UUID, stream_id: UUID, rows: int, object_key: str) -> int:
        self.connection.execute(
            "INSERT OR IGNORE INTO stream_chunk"
            "(chunk_id, stream_id, row_count, object_key, completed_at) VALUES (?, ?, ?, ?, ?)",
            (str(chunk_id), str(stream_id), rows, object_key,
             datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()
        return self.total(stream_id)

    def total(self, stream_id: UUID) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(sum(row_count), 0) FROM stream_chunk WHERE stream_id=?",
            (str(stream_id),),
        ).fetchone()
        return int(row[0])

    def rows(self, chunk_id: UUID) -> int:
        row = self.connection.execute(
            "SELECT row_count FROM stream_chunk WHERE chunk_id=?", (str(chunk_id),)
        ).fetchone()
        return int(row[0])


class SparkStreamChunkIngester:
    def __init__(self, spark=None, minio=None) -> None:
        self.spark = spark or SparkSession.builder.appName(
            "kozmik-stream-ingestion-worker").getOrCreate()
        self.minio = minio or Minio(
            os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )

    async def ingest(
        self, chunk: StreamIngestionChunk, schema: IngestionSchema,
    ) -> tuple[int, str]:
        return await asyncio.to_thread(
            run_spark_operation, "stream-ingestion", self._ingest, chunk, schema)

    def _ingest(
        self, chunk: StreamIngestionChunk, schema: IngestionSchema,
    ) -> tuple[int, str]:
        expected = [column.column_name for column in schema.columns]
        if any(list(record.keys()) != expected for record in chunk.records):
            raise ValueError("SCHEMA_MISMATCH")
        string_schema = spark_types.StructType([
            spark_types.StructField(name, spark_types.StringType(), True) for name in expected
        ])
        raw = self.spark.createDataFrame(
            [[None if record[name] is None else str(record[name]) for name in expected]
             for record in chunk.records],
            schema=string_schema,
        )
        expressions = []
        for column in schema.columns:
            value = spark_fn.trim(spark_fn.col(column.column_name))
            value = spark_fn.when(value == "", None).otherwise(value)
            expressions.append(value.cast(TYPE_REGISTRY[column.data_type]).alias(
                column.column_name))
        governed = raw.select(*expressions)
        rows = governed.count()
        dataset_prefix = f"entities/{schema.entity_id}/streams/{chunk.stream_id}/dataset"
        object_key = f"{dataset_prefix}/part-{chunk.sequence:012d}-{chunk.chunk_id}.parquet"
        with tempfile.TemporaryDirectory(prefix="kozmik-stream-chunk-") as directory:
            output = Path(directory) / "parquet"
            governed.coalesce(1).write.mode("overwrite").parquet(str(output))
            part = next(output.glob("part-*.parquet"))
            self.minio.fput_object("refined", object_key, str(part))
        return rows, object_key


class StreamIngestionProcessor:
    def __init__(self, schema_client, ingester, ledger, publish) -> None:
        self.schema_client = schema_client
        self.ingester = ingester
        self.ledger = ledger
        self.publish = publish

    async def process(
        self, chunk: StreamIngestionChunk, kafka_partition: int = 0, kafka_offset: int = 0,
    ) -> None:
        correlation = str(chunk.chunk_id)
        if self.ledger.completed(chunk.chunk_id):
            schema = await self.schema_client.resolve(chunk.entity)
            object_key = (
                f"entities/{schema.entity_id}/streams/{chunk.stream_id}/dataset/"
                f"part-{chunk.sequence:012d}-{chunk.chunk_id}.parquet")
            await self._event(
                chunk, correlation, kafka_partition, kafka_offset,
                "COMPLETED", "COMPLETED", "IMPORT_COMPLETED",
                self.ledger.rows(chunk.chunk_id), self.ledger.total(chunk.stream_id),
                "refined", object_key,
            )
            return
        try:
            schema = await self.schema_client.resolve(chunk.entity)
            await self._event(chunk, correlation, kafka_partition, kafka_offset,
                              "RECEIVED", "RECEIVED", "IMPORT_RECEIVED")
            await self._event(chunk, correlation, kafka_partition, kafka_offset,
                              "VALIDATING", "VALIDATING", "IMPORT_VALIDATING")
            await self._event(chunk, correlation, kafka_partition, kafka_offset,
                              "RUNNING", "RUNNING", "IMPORT_SPARK_RUNNING")
            rows, object_key = await self.ingester.ingest(chunk, schema)
            await self._event(chunk, correlation, kafka_partition, kafka_offset,
                              "WRITING_RESULTS", "RUNNING", "IMPORT_WRITING_REFINED")
            total = self.ledger.complete(
                chunk.chunk_id, chunk.stream_id, rows, object_key)
            await self._event(chunk, correlation, kafka_partition, kafka_offset,
                              "COMPLETED", "COMPLETED", "IMPORT_COMPLETED",
                              rows, total, "refined", object_key)
        except ValueError as exception:
            code = str(exception)
            if code not in {"UNKNOWN_ENTITY", "SCHEMA_MISMATCH"}:
                code = "IMPORT_FAILED"
            await self._event(chunk, correlation, kafka_partition, kafka_offset,
                              "FAILED", "FAILED", code, error_code=code,
                              )
            raise

    async def _event(
        self, chunk, correlation, kafka_partition, kafka_offset,
        stage, status, code, batch_rows=None, cumulative_rows=None,
        refined_bucket=None,
        refined_key=None, error_code=None, error_message=None,
    ):
        event = StreamIngestionStatusEvent(
            eventId=uuid5(NAMESPACE, f"{chunk.chunk_id}:{stage}"),
            correlationId=correlation, streamId=chunk.stream_id, chunkId=chunk.chunk_id,
            entityId=chunk.entity.id, sourceId=chunk.source_id,
            sequence=chunk.sequence, kafkaPartition=kafka_partition,
            firstOffset=kafka_offset, lastOffset=kafka_offset,
            producedAt=chunk.produced_at, occurredAt=datetime.now(timezone.utc),
            stage=stage, messageCode=code, batchRowCount=batch_rows,
            cumulativeRowCount=cumulative_rows, refinedBucket=refined_bucket,
            refinedObjectKey=refined_key, errorCode=error_code,
        )
        await self.publish(event)


class KafkaStreamIngestionWorker:
    def __init__(self) -> None:
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.topic = os.getenv("KAFKA_STREAM_INGESTION_TOPIC", "ingestion.records.v1")
        self.status_topic = os.getenv(
            "KAFKA_STREAM_STATUS_TOPIC", "ingestion.stream.status.v1")
        self.dlt = self.topic + ".dlt"
        self.consumer = AIOKafkaConsumer(
            self.topic, bootstrap_servers=bootstrap,
            group_id="kozmik-stream-ingestion-worker-v1",
            enable_auto_commit=False, auto_offset_reset="earliest",
            max_partition_fetch_bytes=5 * 1024 * 1024)
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap, enable_idempotence=True, acks="all")
        ledger = StreamChunkLedger(os.getenv(
            "STREAM_INGESTION_LEDGER_PATH", "/tmp/kozmik/stream-ingestion.sqlite3"))
        self.processor = StreamIngestionProcessor(
            SchemaClient(), SparkStreamChunkIngester(), ledger, self.publish)

    async def publish(self, event) -> None:
        await self.producer.send_and_wait(
            self.status_topic, wrap_message(event.model_dump_json(by_alias=True).encode()),
            key=str(event.stream_id).encode())

    async def handle(self, payload: bytes) -> bool:
        try:
            chunk = StreamIngestionChunk.model_validate_json(unwrap_message(payload))
        except (ValueError, ValidationError) as exception:
            logger.warning(
                "stream_ingestion_rejected code=INVALID_MESSAGE exceptionType=%s",
                type(exception).__name__,
            )
            await self.producer.send_and_wait(self.dlt, payload)
            return True
        correlation_token = set_correlation_id(str(chunk.chunk_id))
        try:
            logger.info(
                "stream_chunk_started streamId=%s chunkId=%s entityId=%s",
                chunk.stream_id, chunk.chunk_id, chunk.entity.id,
            )
            await self.processor.process(chunk)
            logger.info("stream_chunk_completed streamId=%s chunkId=%s",
                        chunk.stream_id, chunk.chunk_id)
            return True
        except ValueError as exception:
            logger.warning(
                "stream_chunk_rejected chunkId=%s code=%s",
                chunk.chunk_id, safe_error_code(exception, "STREAM_CHUNK_REJECTED"),
            )
            await self.producer.send_and_wait(self.dlt, payload)
            return True
        except Exception:
            logger.exception("stream_ingestion_failed code=IMPORT_FAILED")
            return False
        finally:
            reset_correlation_id(correlation_token)

    async def run(self) -> None:
        await self.producer.start()
        await self.consumer.start()
        logger.info("stream_ingestion_worker_started topic=%s", self.topic)
        try:
            async for message in self.consumer:
                if await self.handle_with_metadata(
                    message.value, message.partition, message.offset):
                    await self.consumer.commit()
        finally:
            logger.info("stream_ingestion_worker_stopping")
            await self.consumer.stop()
            await self.producer.stop()

    async def handle_with_metadata(
        self, payload: bytes, partition: int, offset: int,
    ) -> bool:
        try:
            chunk = StreamIngestionChunk.model_validate_json(unwrap_message(payload))
        except (ValueError, ValidationError) as exception:
            logger.warning(
                "stream_ingestion_rejected code=INVALID_MESSAGE partition=%s offset=%s "
                "exceptionType=%s",
                partition, offset, type(exception).__name__,
            )
            await self.producer.send_and_wait(self.dlt, payload)
            return True
        correlation_token = set_correlation_id(str(chunk.chunk_id))
        try:
            logger.info(
                "stream_chunk_started streamId=%s chunkId=%s entityId=%s "
                "partition=%s offset=%s",
                chunk.stream_id, chunk.chunk_id, chunk.entity.id, partition, offset,
            )
            await self.processor.process(chunk, partition, offset)
            logger.info("stream_chunk_completed streamId=%s chunkId=%s",
                        chunk.stream_id, chunk.chunk_id)
            return True
        except ValueError as exception:
            logger.warning(
                "stream_chunk_rejected chunkId=%s code=%s",
                chunk.chunk_id, safe_error_code(exception, "STREAM_CHUNK_REJECTED"),
            )
            await self.producer.send_and_wait(self.dlt, payload)
            return True
        except Exception:
            logger.exception("stream_ingestion_failed code=IMPORT_FAILED")
            return False
        finally:
            reset_correlation_id(correlation_token)
