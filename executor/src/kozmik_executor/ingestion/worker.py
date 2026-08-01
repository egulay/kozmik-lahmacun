import asyncio
import json
import os
import re
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote_plus
from uuid import UUID, uuid5

import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from minio import Minio
from pyspark.sql import functions as spark_fn, types as spark_types
from kozmik_executor.spark_runtime import run_spark_operation
from kozmik_executor.spark_session import build_spark_session

from kozmik_executor.execution.worker import EventLedger
from kozmik_executor.chat.providers import ProviderError
from kozmik_executor.messaging_security import wrap_message
from kozmik_executor.logging_config import (
    reset_correlation_id,
    safe_error_code,
    set_correlation_id,
)
from .models import ImportStatusEvent, IngestionColumn, IngestionSchema
from .metadata import MetadataEnricher

NAMESPACE = UUID("d6d71df9-540a-4e8c-9a88-85b2bf4cc9e7")
FILENAME = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}_"
    r"(?P<entity>[0-9a-fA-F-]{36})_(?P<date>\d{8})\.csv$")
TYPE_REGISTRY = {
    "STRING": spark_types.StringType(),
    "INTEGER": spark_types.IntegerType(),
    "LONG": spark_types.LongType(),
    "DECIMAL": spark_types.DecimalType(38, 6),
    "BOOLEAN": spark_types.BooleanType(),
    "DATE": spark_types.DateType(),
    "TIMESTAMP": spark_types.TimestampType(),
}
logger = logging.getLogger(__name__)


def parse_object_created(payload: bytes) -> tuple[UUID, str, str, UUID]:
    document = json.loads(payload)
    records = document.get("Records", [])
    if len(records) != 1 or not str(records[0].get("eventName", "")).startswith("s3:ObjectCreated:"):
        raise ValueError("INVALID_OBJECT_CREATED_EVENT")
    record = records[0]
    bucket = record["s3"]["bucket"]["name"]
    key = unquote_plus(record["s3"]["object"]["key"])
    match = FILENAME.fullmatch(Path(key).name)
    if bucket != "raw" or not match:
        raise ValueError("INVALID_FILENAME")
    entity_id = UUID(match.group("entity"))
    source = f"{bucket}/{key}"
    native_id = str(record.get("responseElements", {}).get("x-minio-origin-endpoint", ""))
    sequencer = str(record["s3"]["object"].get("sequencer", ""))
    source_event_id = uuid5(NAMESPACE, f"{source}:{sequencer}:{native_id}")
    return source_event_id, bucket, key, entity_id


class SchemaClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("JAVA_BASE_URL", "http://localhost:8080")
        self.api_key = os.getenv("INTERNAL_API_KEY", "")

    async def load(self, entity_id: UUID) -> IngestionSchema:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.base_url}/internal/v1/entities/{entity_id}/ingestion-schema",
                headers={"X-Internal-API-Key": self.api_key},
            )
        if response.status_code == 404:
            raise ValueError("UNKNOWN_ENTITY")
        response.raise_for_status()
        return self._project_ingestion_schema(response.json())

    async def resolve(self, descriptor) -> IngestionSchema:
        try:
            existing = await self.load(descriptor.id)
            supplied = [
                (item.column_name, item.data_type)
                for item in descriptor.columns
            ]
            registered = [
                (item.column_name, item.data_type)
                for item in existing.columns
            ]
            if supplied != registered:
                raise ValueError("SCHEMA_MISMATCH")
            return await self.update_categorical_vocabulary(
                descriptor.id, descriptor.columns)
        except ValueError as exception:
            if str(exception) != "UNKNOWN_ENTITY":
                raise
        structure = [
            IngestionColumn(
                columnName=item.column_name,
                dataType=item.data_type,
                categoricalValues=item.categorical_values,
            )
            for item in descriptor.columns
        ]
        enriched = await MetadataEnricher().enrich(
            descriptor.id, descriptor.name, structure)
        return await self.register(enriched)

    async def register_structure(
        self, entity_id: UUID, source_name: str, columns: list[IngestionColumn],
    ) -> IngestionSchema:
        enriched = await MetadataEnricher().enrich(entity_id, source_name, columns)
        return await self.register(enriched)

    async def update_categorical_vocabulary(
        self, entity_id: UUID, columns,
    ) -> IngestionSchema:
        vocabulary = [
            {
                "columnName": item.column_name,
                "values": item.categorical_values,
            }
            for item in columns
            if item.categorical_values
        ]
        if not vocabulary:
            return await self.load(entity_id)
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.put(
                f"{self.base_url}/internal/v1/entities/{entity_id}/categorical-vocabulary",
                headers={"X-Internal-API-Key": self.api_key},
                json={"columns": vocabulary},
            )
        response.raise_for_status()
        return self._project_ingestion_schema(response.json())

    async def register(self, descriptor) -> IngestionSchema:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.base_url}/internal/v1/entities/stream-registry/resolve",
                headers={"X-Internal-API-Key": self.api_key},
                json=descriptor.model_dump(by_alias=True, mode="json"),
            )
        if response.status_code == 409:
            raise ValueError("SCHEMA_MISMATCH")
        response.raise_for_status()
        return self._project_ingestion_schema(response.json())

    @staticmethod
    def _project_ingestion_schema(document: dict) -> IngestionSchema:
        """Accept only the governed fields required by the Spark ingestion boundary."""
        return IngestionSchema.model_validate({
            "schemaVersion": document["schemaVersion"],
            "entityId": document["entityId"],
            "columns": [
                {
                    "columnName": column["columnName"],
                    "dataType": column["dataType"],
                }
                for column in document["columns"]
            ],
        })


class SparkCsvIngester:
    def __init__(self, spark=None, minio=None) -> None:
        self.spark = spark or build_spark_session("kozmik-ingestion-worker")
        self.minio = minio or Minio(
            os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )

    async def ingest(
        self, import_id: UUID, bucket: str, key: str, schema: IngestionSchema,
    ) -> tuple[int, str, int]:
        return await asyncio.to_thread(
            run_spark_operation, "csv-ingestion",
            self._ingest, import_id, bucket, key, schema)

    async def discover(self, bucket: str, key: str) -> list[IngestionColumn]:
        return await asyncio.to_thread(
            run_spark_operation, "schema-discovery", self._discover, bucket, key)

    def _discover(self, bucket: str, key: str) -> list[IngestionColumn]:
        with tempfile.TemporaryDirectory(prefix="kozmik-discovery-") as directory:
            source = Path(directory) / "source.csv"
            response = self.minio.get_object(bucket, key)
            try:
                with source.open("wb") as stream:
                    for chunk in response.stream(1024 * 1024):
                        stream.write(chunk)
            finally:
                response.close()
                response.release_conn()
            frame = (self.spark.read.option("header", True).option("inferSchema", True)
                     .option("samplingRatio", 0.1).csv(str(source)))
            reverse_types = (
                (spark_types.BooleanType, "BOOLEAN"),
                (spark_types.IntegerType, "INTEGER"),
                (spark_types.LongType, "LONG"),
                (spark_types.FloatType, "DECIMAL"),
                (spark_types.DoubleType, "DECIMAL"),
                (spark_types.DecimalType, "DECIMAL"),
                (spark_types.DateType, "DATE"),
                (spark_types.TimestampType, "TIMESTAMP"),
            )
            return [
                IngestionColumn(
                    columnName=field.name,
                    dataType=next(
                        (name for spark_type, name in reverse_types
                         if isinstance(field.dataType, spark_type)),
                        "STRING",
                    ),
                    categoricalValues=self._categorical_values(frame, field),
                )
                for field in frame.schema.fields
            ]

    @staticmethod
    def _categorical_values(frame, field) -> list[str]:
        if not isinstance(field.dataType, spark_types.StringType):
            return []
        normalized_name = field.name.lower()
        if normalized_name == "id" or normalized_name.endswith("_id"):
            return []
        values = [
            str(row[0]) for row in
            frame.select(spark_fn.trim(spark_fn.col(field.name)))
            .where(spark_fn.col(field.name).isNotNull())
            .distinct().limit(33).collect()
            if row[0] is not None and str(row[0]).strip()
        ]
        return sorted(values) if len(values) <= 32 else []

    def _ingest(
        self, import_id: UUID, bucket: str, key: str, schema: IngestionSchema,
    ) -> tuple[int, str, int]:
        with tempfile.TemporaryDirectory(prefix="kozmik-import-") as directory:
            source = Path(directory) / "source.csv"
            response = self.minio.get_object(bucket, key)
            try:
                with source.open("wb") as stream:
                    for chunk in response.stream(1024 * 1024):
                        stream.write(chunk)
            finally:
                response.close()
                response.release_conn()
            raw = self.spark.read.option("header", True).option("mode", "FAILFAST").csv(str(source))
            expected = [item.column_name for item in schema.columns]
            if raw.columns != expected:
                raise ValueError("SCHEMA_MISMATCH")
            expressions = []
            for item in schema.columns:
                value = spark_fn.trim(spark_fn.col(item.column_name))
                value = spark_fn.when(value == "", None).otherwise(value)
                expressions.append(value.cast(TYPE_REGISTRY[item.data_type]).alias(item.column_name))
            governed = raw.select(*expressions)
            rows = governed.count()
            output = Path(directory) / "refined"
            governed.coalesce(1).write.mode("overwrite").parquet(str(output))
            part = next(output.glob("part-*.parquet"))
            object_key = (
                f"entities/{schema.entity_id}/imports/{import_id}/"
                "data.parquet"
            )
            self.minio.fput_object("refined", object_key, str(part))
            return rows, object_key, part.stat().st_size


class IngestionProcessor:
    def __init__(self, schema_client, ingester, publish) -> None:
        self.schema_client = schema_client
        self.ingester = ingester
        self.publish = publish

    async def process(self, source_event_id, bucket, key, entity_id) -> None:
        import_id = uuid5(NAMESPACE, f"import:{source_event_id}")
        correlation = str(import_id)
        try:
            await self._event(import_id, source_event_id, entity_id, key, correlation,
                              "RECEIVED", "RECEIVED", "IMPORT_RECEIVED")
            structure = await self.ingester.discover(bucket, key)
            try:
                schema = await self.schema_client.load(entity_id)
                registered = [
                    item.column_name for item in schema.columns
                ]
                supplied = [
                    item.column_name for item in structure
                ]
                if registered != supplied:
                    raise ValueError("SCHEMA_MISMATCH")
                discovered_by_name = {item.column_name: item for item in structure}
                vocabulary = [IngestionColumn(
                    columnName=item.column_name,
                    dataType=item.data_type,
                    categoricalValues=(
                        discovered_by_name[item.column_name].categorical_values
                        if item.data_type == "STRING" else []
                    ),
                ) for item in schema.columns]
                schema = await self.schema_client.update_categorical_vocabulary(
                    entity_id, vocabulary)
            except ValueError as exception:
                if str(exception) != "UNKNOWN_ENTITY":
                    raise
                source_name = Path(key).name.rsplit(f"_{entity_id}_", 1)[0]
                schema = await self.schema_client.register_structure(
                    entity_id, source_name, structure)
            await self._event(import_id, source_event_id, entity_id, key, correlation,
                              "VALIDATING", "VALIDATING", "IMPORT_VALIDATING")
            await self._event(import_id, source_event_id, entity_id, key, correlation,
                              "RUNNING", "RUNNING", "IMPORT_SPARK_RUNNING")
            rows, refined_key, _ = await self.ingester.ingest(import_id, bucket, key, schema)
            await self._event(import_id, source_event_id, entity_id, key, correlation,
                              "WRITING_RESULTS", "RUNNING", "IMPORT_WRITING_REFINED")
            await self._event(import_id, source_event_id, entity_id, key, correlation,
                              "COMPLETED", "COMPLETED", "IMPORT_COMPLETED",
                              rows=rows, refined_bucket="refined", refined_key=refined_key)
        except (ValueError, ProviderError) as exception:
            code = exception.code if isinstance(exception, ProviderError) else str(exception)
            if code not in {
                "UNKNOWN_ENTITY",
                "SCHEMA_MISMATCH",
                "METADATA_ENRICHMENT_INVALID",
                "METADATA_COLUMN_BINDING_MISMATCH",
            }:
                code = "IMPORT_FAILED"
            await self._event(import_id, source_event_id, entity_id, key, correlation,
                              "FAILED", "FAILED", "IMPORT_FAILED", error_code=code,
                              error_message=(
                                  "The source could not be registered with governed metadata"
                                  if code.startswith("METADATA_")
                                  else "Import rejected by governed validation"
                              ))
            raise

    async def _event(
        self, import_id, source_event_id, entity_id, key, correlation, stage, status, code,
        rows=None, refined_bucket=None, refined_key=None,
        error_code=None, error_message=None,
    ):
        event = ImportStatusEvent(
            eventId=uuid5(NAMESPACE, f"{source_event_id}:{stage}"),
            correlationId=correlation, importId=import_id, sourceEventId=source_event_id,
            entityId=entity_id,
            occurredAt=datetime.now(timezone.utc), sourceReference=f"raw/{key}",
            stage=stage, status=status, messageCode=code, rowCount=rows,
            refinedBucket=refined_bucket, refinedObjectKey=refined_key,
            errorCode=error_code, errorMessage=error_message,
        )
        await self.publish(event)


class KafkaIngestionWorker:
    def __init__(self) -> None:
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.topic = os.getenv("KAFKA_INGESTION_EVENT_TOPIC", "ingestion.events.v1")
        self.status_topic = os.getenv("KAFKA_INGESTION_STATUS_TOPIC", "ingestion.status.v1")
        self.dlt = self.topic + ".dlt"
        self.consumer = AIOKafkaConsumer(
            self.topic, bootstrap_servers=bootstrap, group_id="kozmik-ingestion-worker-v1",
            enable_auto_commit=False, auto_offset_reset="earliest")
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap, enable_idempotence=True, acks="all")
        self.ledger = EventLedger(os.getenv(
            "INGESTION_EVENT_LEDGER_PATH", "/tmp/kozmik/ingestion-events.sqlite3"))
        self.processor = IngestionProcessor(SchemaClient(), SparkCsvIngester(), self.publish)

    async def publish(self, event):
        await self.producer.send_and_wait(
            self.status_topic,
            wrap_message(event.model_dump_json(by_alias=True).encode()),
            key=str(event.import_id).encode())

    async def handle(self, payload: bytes) -> bool:
        try:
            source_event_id, bucket, key, entity_id = parse_object_created(payload)
        except Exception as exception:
            logger.warning(
                "ingestion_event_rejected code=INVALID_MESSAGE exceptionType=%s",
                type(exception).__name__,
            )
            await self.producer.send_and_wait(self.dlt, payload)
            return True
        if self.ledger.completed(source_event_id):
            logger.info("ingestion_event_duplicate eventId=%s", source_event_id)
            return True
        correlation_token = set_correlation_id(str(source_event_id))
        try:
            logger.info(
                "ingestion_started eventId=%s entityId=%s bucket=%s",
                source_event_id, entity_id, bucket,
            )
            await self.processor.process(source_event_id, bucket, key, entity_id)
            self.ledger.complete(source_event_id)
            logger.info("ingestion_completed eventId=%s entityId=%s",
                        source_event_id, entity_id)
            return True
        except (ValueError, ProviderError) as exception:
            logger.warning(
                "ingestion_rejected eventId=%s code=%s",
                source_event_id, safe_error_code(exception, "IMPORT_REJECTED"),
            )
            await self.producer.send_and_wait(self.dlt, payload)
            self.ledger.complete(source_event_id)
            return True
        except Exception:
            logger.exception("ingestion_failed code=IMPORT_FAILED")
            if self.ledger.failed_attempt(source_event_id) >= 3:
                logger.error("ingestion_dead_lettered eventId=%s", source_event_id)
                await self.producer.send_and_wait(self.dlt, payload)
                self.ledger.complete(source_event_id)
                return True
            return False
        finally:
            reset_correlation_id(correlation_token)

    async def run(self):
        await self.producer.start()
        await self.consumer.start()
        logger.info("ingestion_worker_started topic=%s", self.topic)
        try:
            async for message in self.consumer:
                if await self.handle(message.value):
                    await self.consumer.commit()
        finally:
            logger.info("ingestion_worker_stopping")
            await self.consumer.stop()
            await self.producer.stop()


def main() -> None:
    asyncio.run(KafkaIngestionWorker().run())
