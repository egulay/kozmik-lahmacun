import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pyspark.sql import SparkSession

from kozmik_executor.ingestion.models import IngestionColumn, IngestionSchema
from kozmik_executor.ingestion.models import StreamIngestionChunk
from kozmik_executor.ingestion.stream import (
    StreamChunkLedger,
    StreamIngestionProcessor,
    SparkStreamChunkIngester,
)
from kozmik_executor.ingestion.worker import (
    IngestionProcessor,
    SchemaClient,
    SparkCsvIngester,
    parse_object_created,
)
from kozmik_executor.chat.providers import ProviderError

ENTITY = UUID("11111111-1111-4111-8111-111111111111")


def notification(name=None, event_name="s3:ObjectCreated:Put"):
    name = name or (
        "incoming/sales_11111111-1111-4111-8111-111111111111_20260728.csv")
    return json.dumps({"Records": [{
        "eventName": event_name,
        "responseElements": {"x-minio-origin-endpoint": "minio"},
        "s3": {"bucket": {"name": "raw"}, "object": {"key": name, "sequencer": "abc"}},
    }]}).encode()


def test_filename_contract_and_event_identity_are_deterministic():
    first = parse_object_created(notification())
    second = parse_object_created(notification())
    assert first == second
    assert first[3] == ENTITY


def test_java_governance_metadata_is_explicitly_projected_for_ingestion():
    projected = SchemaClient._project_ingestion_schema({
        "schemaVersion": "1.0",
        "entityId": str(ENTITY),
        "columns": [{
            "id": str(uuid4()),
            "columnName": "sale_id",
            "businessName": "Sale ID",
            "dataType": "STRING",





        }],
    })

    assert projected.entity_id == ENTITY
    assert projected.columns[0].column_name == "sale_id"


@pytest.mark.parametrize("name", [
    "incoming/sales.csv",
    "incoming/sales_not-a-uuid_20260728.csv",
    "incoming/sales_11111111-1111-4111-8111-111111111111_bad.csv",
    "incoming/sales_11111111-1111-4111-8111-111111111111_2026-07-28.csv",
])
def test_invalid_filenames_are_rejected(name):
    with pytest.raises(ValueError, match="INVALID_FILENAME"):
        parse_object_created(notification(name))


class ObjectResponse:
    def __init__(self, data):
        self.data = data

    def stream(self, size):
        yield self.data

    def close(self):
        pass

    def release_conn(self):
        pass


class MemoryMinio:
    def __init__(self, data):
        self.data = data
        self.upload = None

    def get_object(self, bucket, key):
        return ObjectResponse(self.data)

    def fput_object(self, bucket, key, path):
        self.upload = (bucket, key)


@pytest.fixture(scope="module")
def spark():
    session = (SparkSession.builder.master("local[2]").appName("kozmik-ingestion-test")
               .config("spark.ui.enabled", "false").getOrCreate())
    yield session
    session.stop()


def schema():
    return IngestionSchema.model_validate({
        "schemaVersion": "1.0", "entityId": str(ENTITY),
        "columns": [
            {"columnName": "sale_id", "dataType": "STRING"},
            {"columnName": "quantity", "dataType": "INTEGER"},
            {"columnName": "net_amount", "dataType": "DECIMAL"},
        ],
    })


def test_spark_csv_schema_enforcement_and_governed_parquet(spark):
    store = MemoryMinio(b"sale_id,quantity,net_amount\n S-1 ,2,10.50\nS-2,3,20.00\n")
    import_id = uuid4()
    rows, key, size = asyncio.run(
        SparkCsvIngester(spark, store).ingest(import_id, "raw", "incoming/source.csv", schema()))
    assert rows == 2
    assert key.startswith(f"entities/{ENTITY}/imports/{import_id}/")
    assert size > 0
    assert store.upload == ("refined", key)


def test_spark_csv_schema_mismatch_is_rejected(spark):
    store = MemoryMinio(b"sale_id,wrong,net_amount\nS-1,2,10.50\n")
    with pytest.raises(ValueError, match="SCHEMA_MISMATCH"):
        asyncio.run(SparkCsvIngester(spark, store).ingest(
            uuid4(), "raw", "incoming/source.csv", schema()))


def test_object_created_to_completed_status_end_to_end(spark):
    source_event, bucket, key, entity_id = parse_object_created(notification())
    governed_schema = schema()
    store = MemoryMinio(b"sale_id,quantity,net_amount\nS-1,2,10.50\n")
    published = []

    class SchemaClient:
        async def load(self, requested_entity):
            assert requested_entity == entity_id
            return governed_schema

    async def publish(event):
        published.append(event)

    asyncio.run(IngestionProcessor(
        SchemaClient(), SparkCsvIngester(spark, store), publish,
    ).process(source_event, bucket, key, entity_id))
    assert [event.stage for event in published] == [
        "RECEIVED", "VALIDATING", "RUNNING", "WRITING_RESULTS", "COMPLETED",
    ]
    assert published[-1].row_count == 1
    assert published[-1].refined_object_key == store.upload[1]


def test_metadata_failure_publishes_terminal_import_status():
    source_event, bucket, key, entity_id = parse_object_created(notification())
    published = []

    class SchemaClient:
        async def load(self, _requested_entity):
            raise ValueError("UNKNOWN_ENTITY")

        async def register_structure(self, *_arguments):
            raise ProviderError("METADATA_ENRICHMENT_INVALID")

    class Ingester:
        async def discover(self, _bucket, _key):
            return [IngestionColumn(columnName="sale_id", dataType="STRING")]

    async def publish(event):
        published.append(event)

    with pytest.raises(ProviderError, match="METADATA_ENRICHMENT_INVALID"):
        asyncio.run(IngestionProcessor(
            SchemaClient(), Ingester(), publish,
        ).process(source_event, bucket, key, entity_id))

    assert published[-1].status == "FAILED"
    assert published[-1].error_code == "METADATA_ENRICHMENT_INVALID"


def test_cdr_kafka_chunks_append_to_governed_dataset_and_report_cumulative_rows(
    spark, tmp_path,
):
    cdr_entity = UUID("22222222-2222-4222-8222-222222222222")
    stream_id = uuid4()
    governed_schema = IngestionSchema.model_validate({
        "schemaVersion": "1.0", "entityId": str(cdr_entity),
        "columns": [
            {"columnName": "cdr_id", "dataType": "STRING"},
            {"columnName": "event_time", "dataType": "TIMESTAMP"},
            {"columnName": "duration_seconds", "dataType": "INTEGER"},
        ],
    })

    class AppendMinio:
        def __init__(self):
            self.uploads = []

        def fput_object(self, bucket, key, path):
            self.uploads.append((bucket, key))

    class SchemaClient:
        async def resolve(self, descriptor):
            assert descriptor.id == cdr_entity
            return governed_schema

    def chunk(sequence, records):
        entity = {
            "id": str(cdr_entity), "name": "Example stream",

            "columns": [
                {"columnName": "cdr_id", "businessName": "ID", "dataType": "STRING",

                 "ordinalPosition": 1,
},
                {"columnName": "event_time", "businessName": "Time",
                 "dataType": "TIMESTAMP",
 "ordinalPosition": 2,

},
                {"columnName": "duration_seconds", "businessName": "Duration",
                 "dataType": "INTEGER",
 "ordinalPosition": 3,

},
            ],
        }
        return StreamIngestionChunk(
            chunkId=uuid4(), streamId=stream_id, entity=entity,
            sourceId="tower-42", producedAt=datetime.now(timezone.utc),
            sequence=sequence, records=records,
        )

    store = AppendMinio()
    published = []

    async def publish(event):
        published.append(event)

    processor = StreamIngestionProcessor(
        SchemaClient(), SparkStreamChunkIngester(spark, store),
        StreamChunkLedger(str(tmp_path / "cdr.sqlite3")), publish,
    )
    asyncio.run(processor.process(chunk(0, [
        {"cdr_id": "C-1", "event_time": "2026-01-01T00:00:00Z",
         "duration_seconds": "10"},
        {"cdr_id": "C-2", "event_time": "2026-01-01T00:01:00Z",
         "duration_seconds": "20"},
    ])))
    second = chunk(1, [
        {"cdr_id": "C-3", "event_time": "2026-01-01T00:02:00Z",
         "duration_seconds": "30"},
    ])
    asyncio.run(processor.process(second))
    asyncio.run(processor.process(second))

    assert len(store.uploads) == 2
    assert all("/dataset/part-" in key for _, key in store.uploads)
    completed = [event for event in published if event.stage == "COMPLETED"]
    assert [event.batch_row_count for event in completed] == [2, 1, 1]
    assert [event.cumulative_row_count for event in completed] == [2, 3, 3]
    assert completed[-1].event_id == completed[-2].event_id
    assert completed[-1].topic == "ingestion.records.v1"
    assert completed[-1].refined_object_key.endswith(".parquet")
