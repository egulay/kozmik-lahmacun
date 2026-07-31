import asyncio
import json
import os
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import OffsetAndMetadata, TopicPartition
from minio import Minio
from pydantic import ValidationError

from .models import (
    ArtifactRetentionCommand, ArtifactRetentionEvent, ExecutionCommand,
    ExecutionControlCommand, ExecutionResultNotification, ExecutionStatusEvent,
)
from kozmik_executor.lifecycle import lifecycle_coordinator
from .spark_report import SparkReportExecutor
from .spark_ml import SparkMlExecutor
from .explanation import ResultExplainer
from .failure_explanation import FailureExplainer, SanitizedFailure
from .dataset import GovernedDatasetResolver
from kozmik_executor.planning.ml import ALGORITHM_REGISTRY
from kozmik_executor.messaging_security import unwrap_message, wrap_message
from kozmik_executor.logging_config import reset_correlation_id, set_correlation_id

EVENT_NAMESPACE = UUID("b6fc9c27-4ed8-4c43-89a2-82e7a41215e7")
logger = logging.getLogger(__name__)


def _spark_runtime_unavailable(exception: BaseException) -> bool:
    markers = (
        "sparkcontext was shut down",
        "stopped sparkcontext",
        "cannot call methods on a stopped sparkcontext",
        "connection refused",
        "answer from java side is empty",
        "broken pipe",
        "java gateway process exited",
    )
    current: BaseException | None = exception
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if any(marker in str(current).lower() for marker in markers):
            return True
        current = current.__cause__ or current.__context__
    return False


def _spark_tuning_configuration_unsafe(exception: BaseException) -> bool:
    current: BaseException | None = exception
    visited: set[int] = set()
    messages: list[str] = []
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        messages.append(str(current).lower())
        current = current.__cause__ or current.__context__
    message = " ".join(messages)
    return "task serialization failed" in message and "stackoverflowerror" in message


def validate_execution_command(command: ExecutionCommand) -> None:
    roles = command.authorization.get("roles", [])
    actor = command.authorization.get("actorUserId")
    if (
        not isinstance(roles, list)
        or actor != str(command.actor_user_id)
        or command.order.entity_id != command.entity_id
        or command.order.execution_type != command.execution_type
    ):
        raise ValueError("EXECUTION_ORDER_INVALID")
    if command.execution_type == "ML":
        if not set(roles).intersection({"SCIENTIST", "ADMIN"}):
            raise ValueError("EXECUTION_ORDER_INVALID")
        key = (command.order.payload.problem_type, command.order.payload.algorithm)
        definition = ALGORITHM_REGISTRY.get(key)
        if definition is None or not set(command.order.payload.metrics).issubset(
            definition["metrics"]
        ):
            raise ValueError("EXECUTION_ORDER_INVALID")
        if command.order.payload.candidate_algorithms:
            selection = command.order.payload.selection
            total_trials = 0
            for candidate in command.order.payload.candidate_algorithms:
                candidate_definition = ALGORITHM_REGISTRY.get(
                    (command.order.payload.problem_type, candidate.algorithm))
                if (
                    candidate_definition is None
                    or selection.primary_metric not in candidate_definition["metrics"]
                ):
                    raise ValueError("EXECUTION_ORDER_INVALID")
                combinations = 1
                for values in candidate.parameter_grid.values():
                    combinations *= len(values)
                total_trials += combinations
            if total_trials > selection.maximum_trials:
                raise ValueError("EXECUTION_ORDER_INVALID")
        analysis = command.order.payload.what_if_analysis
        if analysis is not None:
            if command.order.payload.problem_type != "REGRESSION":
                raise ValueError("EXECUTION_ORDER_INVALID")
            scenario_codes = [scenario.code for scenario in analysis.scenarios]
            if len(scenario_codes) != len(set(scenario_codes)):
                raise ValueError("EXECUTION_ORDER_INVALID")
            approved_features = set(command.order.payload.feature_columns)
            for scenario in analysis.scenarios:
                changed = [change.column for change in scenario.changes]
                if (
                    len(changed) != len(set(changed))
                    or not set(changed).issubset(approved_features)
                ):
                    raise ValueError("EXECUTION_ORDER_INVALID")
    elif not set(roles).intersection({"REPORTER", "SCIENTIST", "ADMIN"}):
        raise ValueError("EXECUTION_ORDER_INVALID")


class EventLedger:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS processed_event "
            "(event_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS event_attempt "
            "(event_id TEXT PRIMARY KEY, attempt_count INTEGER NOT NULL)"
        )
        self.connection.commit()

    def completed(self, event_id: UUID) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM processed_event WHERE event_id=?", (str(event_id),)
        ).fetchone() is not None

    def complete(self, event_id: UUID) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO processed_event(event_id, completed_at) VALUES (?, ?)",
            (str(event_id), datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def failed_attempt(self, event_id: UUID) -> int:
        self.connection.execute(
            "INSERT INTO event_attempt(event_id, attempt_count) VALUES (?, 1) "
            "ON CONFLICT(event_id) DO UPDATE SET attempt_count=attempt_count+1",
            (str(event_id),),
        )
        self.connection.commit()
        return self.connection.execute(
            "SELECT attempt_count FROM event_attempt WHERE event_id=?", (str(event_id),)
        ).fetchone()[0]


class TrustedReportWorker:
    def __init__(
        self,
        publish_status: Callable[[ExecutionStatusEvent], Awaitable[None]],
        publish_result: Callable[[ExecutionResultNotification], Awaitable[None]],
        executor: SparkReportExecutor,
        ml_executor: SparkMlExecutor | None = None,
        explainer: ResultExplainer | None = None,
        dataset_resolver: GovernedDatasetResolver | None = None,
    ) -> None:
        self.publish_status = publish_status
        self.publish_result = publish_result
        self.executor = executor
        self.ml_executor = ml_executor
        self.explainer = explainer or ResultExplainer()
        self.dataset_resolver = dataset_resolver

    async def execute(
        self, command: ExecutionCommand, cancelled: asyncio.Event | None = None
    ) -> None:
        validate_execution_command(command)
        cancelled = cancelled or asyncio.Event()
        stages = [
            ("QUEUED", "QUEUED", 0, "EXECUTION_QUEUED"),
            ("PREPARING", "RUNNING", 10, "EXECUTION_PREPARING"),
            ("VALIDATING", "RUNNING", 20, "EXECUTION_VALIDATING"),
            ("RESOLVING_DATA", "RUNNING", 25, "EXECUTION_RESOLVING_DATA"),
        ]
        if (
            command.execution_type == "ML"
            and command.order.payload.candidate_algorithms
        ):
            stages.append(("TUNING", "RUNNING", 30, "EXECUTION_ML_TUNING"))
        stages.append(
            (("TRAINING" if command.execution_type == "ML" else "RUNNING"),
             "RUNNING", 40,
             ("EXECUTION_ML_TRAINING" if command.execution_type == "ML"
              else "EXECUTION_SPARK_RUNNING"))
        )
        for stage, status, progress, code in stages:
            await self._status(command, stage, status, progress, code)
        selected = self.ml_executor if command.execution_type == "ML" else self.executor
        if selected is None:
            raise ValueError("ALGORITHM_NOT_ALLOWED")
        if self.dataset_resolver is None:
            result = await selected.execute(
                command.execution_id, command.order, command.configuration, cancelled)
        else:
            async with self.dataset_resolver.resolve(command) as dataset:
                configuration = dict(command.configuration)
                execution = dict(configuration.get("execution", {}))
                execution.update(dataset)
                configuration["execution"] = execution
                result = await selected.execute(
                    command.execution_id, command.order, configuration, cancelled)
        if cancelled.is_set():
            raise asyncio.CancelledError
        await self._status(
            command, "WRITING_RESULTS", "RUNNING", 80, "EXECUTION_WRITING_RESULTS")
        await self._status(command, "SUMMARIZING", "RUNNING", 90, "EXECUTION_SUMMARIZING")
        explanation = await self.explainer.explain(command, result)
        result["summaryStatus"] = explanation.status
        result["managementSummary"] = explanation.text
        await self.publish_result(ExecutionResultNotification(
            schema_version="1.0",
            event_id=uuid5(EVENT_NAMESPACE, f"{command.event_id}:result"),
            correlation_id=command.correlation_id, execution_id=command.execution_id,
            entity_id=command.entity_id, actor_user_id=command.actor_user_id,
            occurred_at=datetime.now(timezone.utc), status="SUCCEEDED",
            result_code="EXECUTION_RESULT_READY", **result,
        ))
        await self._status(
            command, "COMPLETED", "SUCCEEDED", 100, "EXECUTION_REPORT_COMPLETED")

    async def _status(
        self, command: ExecutionCommand, stage: str, status: str, progress: int, code: str,
    ) -> None:
        await self.publish_status(ExecutionStatusEvent(
            schema_version="1.0",
            event_id=uuid5(EVENT_NAMESPACE, f"{command.event_id}:status:{stage}"),
            correlation_id=command.correlation_id, execution_id=command.execution_id,
            entity_id=command.entity_id, actor_user_id=command.actor_user_id,
            occurred_at=datetime.now(timezone.utc), stage=stage, status=status,
            progress_percent=progress, message_code=code, details={"engine": "spark"},
        ))


class KafkaExecutionWorker:
    def __init__(self) -> None:
        bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.command_topic = os.getenv("KAFKA_EXECUTION_COMMAND_TOPIC", "execution.commands.v1")
        self.control_topic = os.getenv("KAFKA_EXECUTION_CONTROL_TOPIC", "execution.control.v1")
        self.event_topic = os.getenv("KAFKA_EXECUTION_EVENT_TOPIC", "execution.events.v1")
        self.result_topic = os.getenv("KAFKA_EXECUTION_RESULT_TOPIC", "execution.results.v1")
        self.dead_letter_topic = self.command_topic + ".dlt"
        self.consumer = AIOKafkaConsumer(
            self.command_topic, bootstrap_servers=bootstrap,
            group_id=os.getenv("KAFKA_PYTHON_GROUP_ID", "kozmik-python-worker-v1"),
            enable_auto_commit=False, auto_offset_reset="earliest",
        )
        self.control_consumer = AIOKafkaConsumer(
            self.control_topic, bootstrap_servers=bootstrap,
            group_id=os.getenv("KAFKA_PYTHON_CONTROL_GROUP_ID", "kozmik-python-control-v1"),
            enable_auto_commit=False, auto_offset_reset="earliest",
        )
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap, enable_idempotence=True, acks="all")
        self.minio = Minio(
            os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )
        self.ledger = EventLedger(os.getenv(
            "EXECUTION_EVENT_LEDGER_PATH", "/tmp/kozmik/execution-events.sqlite3"))
        self.semaphore = asyncio.Semaphore(int(os.getenv("SPARK_MAX_CONCURRENT_JOBS", "4")))
        self.worker = TrustedReportWorker(
            self.publish_status, self.publish_result, SparkReportExecutor(), SparkMlExecutor(),
            dataset_resolver=GovernedDatasetResolver())
        self.failure_explainer = FailureExplainer()
        self.lifecycle = lifecycle_coordinator
        self.tasks: set[asyncio.Task] = set()

    async def publish_status(self, event: ExecutionStatusEvent) -> None:
        await self._send(self.event_topic, event.execution_id, event)

    async def publish_result(self, event: ExecutionResultNotification) -> None:
        await self._send(self.result_topic, event.execution_id, event)

    async def _send(self, topic: str, key: UUID, event) -> None:
        value = wrap_message(event.model_dump_json(by_alias=True).encode())
        for attempt in range(3):
            try:
                await self.producer.send_and_wait(topic, value, key=str(key).encode())
                return
            except Exception as exception:
                if attempt == 2:
                    raise
                logger.warning(
                    "kafka_publish_retry topic=%s attempt=%s exceptionType=%s",
                    topic, attempt + 1, type(exception).__name__,
                )
                await asyncio.sleep(0.1 * (2**attempt))

    async def handle(self, value: bytes) -> bool:
        try:
            payload = unwrap_message(value)
            command = ExecutionCommand.model_validate_json(payload)
        except (ValidationError, ValueError) as exception:
            logger.warning(
                "execution_command_rejected code=INVALID_MESSAGE exceptionType=%s",
                type(exception).__name__,
            )
            await self.producer.send_and_wait(self.dead_letter_topic, value)
            return True
        if self.ledger.completed(command.event_id):
            logger.info("execution_command_duplicate eventId=%s", command.event_id)
            return True
        correlation_token = set_correlation_id(command.correlation_id)
        cancelled = asyncio.Event()
        try:
            logger.info(
                "execution_started executionId=%s eventId=%s type=%s",
                command.execution_id, command.event_id, command.execution_type,
            )
            async with self.semaphore:
                selected = (self.worker.ml_executor if command.execution_type == "ML"
                            else self.worker.executor)
                registered = await self.lifecycle.register(
                    command.execution_id, cancelled,
                    lambda: selected.cancel(command.execution_id),
                )
                if not registered:
                    logger.warning(
                        "execution_deferred executionId=%s reason=EXECUTOR_DRAINING",
                        command.execution_id,
                    )
                    return False
                try:
                    await self.worker.execute(command, cancelled)
                finally:
                    await self.lifecycle.complete(command.execution_id)
            self.ledger.complete(command.event_id)
            logger.info(
                "execution_completed executionId=%s eventId=%s",
                command.execution_id, command.event_id,
            )
            return True
        except asyncio.TimeoutError:
            logger.warning("execution_timed_out executionId=%s", command.execution_id)
            await self.publish_status(self._failure(command, "TIMED_OUT", "EXECUTION_TIMEOUT"))
            self.ledger.complete(command.event_id)
            return True
        except asyncio.CancelledError:
            logger.warning("execution_cancelled executionId=%s", command.execution_id)
            await self.publish_status(
                self._failure(command, "CANCELLED", "EXECUTION_CANCELLED"))
            self.ledger.complete(command.event_id)
            return True
        except ValueError as exception:
            code = str(exception)
            safe_code = (
                code if code in {
                    "EXECUTION_ORDER_INVALID",
                    "SCHEMA_VERSION_MISMATCH",
                    "GOVERNED_DATASET_NOT_FOUND",
                    "GOVERNED_DATASET_BINDING_MISMATCH",
                }
                else "SPARK_JOB_FAILED"
            )
            logger.warning(
                "execution_rejected executionId=%s code=%s",
                command.execution_id, safe_code,
            )
            failure = await self.failure_explainer.explain(command, exception, safe_code)
            await self.publish_status(
                self._failure(command, "FAILED", safe_code, failure))
            self.ledger.complete(command.event_id)
            return True
        except Exception as exception:
            if cancelled.is_set():
                logger.warning(
                    "execution_cancelled executionId=%s duringSparkShutdown=true",
                    command.execution_id,
                )
                await self.publish_status(
                    self._failure(command, "CANCELLED", "EXECUTION_CANCELLED"))
                self.ledger.complete(command.event_id)
                return True
            safe_code = (
                "ML_TUNING_CONFIGURATION_UNSAFE"
                if _spark_tuning_configuration_unsafe(exception)
                else (
                    "SPARK_RUNTIME_UNAVAILABLE"
                    if _spark_runtime_unavailable(exception)
                    else "SPARK_JOB_FAILED"
                )
            )
            logger.exception("execution_failed code=%s", safe_code)
            failure = await self.failure_explainer.explain(
                command, exception, safe_code)
            await self.publish_status(
                self._failure(command, "FAILED", safe_code, failure))
            if self.ledger.failed_attempt(command.event_id) >= 3:
                logger.error(
                    "execution_dead_lettered executionId=%s eventId=%s",
                    command.execution_id, command.event_id,
                )
                await self.producer.send_and_wait(self.dead_letter_topic, value)
                self.ledger.complete(command.event_id)
                return True
            return False
        finally:
            reset_correlation_id(correlation_token)

    async def handle_control(self, value: bytes) -> bool:
        try:
            payload = unwrap_message(value)
            operation = json.loads(payload).get("operation")
            if operation == "DELETE_ARTIFACT":
                return await self._delete_artifact(
                    ArtifactRetentionCommand.model_validate_json(payload))
            command = ExecutionControlCommand.model_validate_json(payload)
        except (ValidationError, ValueError) as exception:
            logger.warning(
                "execution_control_rejected code=INVALID_MESSAGE exceptionType=%s",
                type(exception).__name__,
            )
            await self.producer.send_and_wait(self.control_topic + ".dlt", value)
            return True
        if self.ledger.completed(command.event_id):
            return True
        cancelled = await self.lifecycle.cancel(command.execution_id)
        logger.info(
            "execution_cancel_requested executionId=%s active=%s",
            command.execution_id, cancelled,
        )
        self.ledger.complete(command.event_id)
        return True

    async def _delete_artifact(self, command: ArtifactRetentionCommand) -> bool:
        if self.ledger.completed(command.event_id):
            logger.info(
                "artifact_retention_duplicate artifactId=%s eventId=%s",
                command.artifact_id, command.event_id,
            )
            return True
        correlation_token = set_correlation_id(command.correlation_id)
        status = "SUCCEEDED"
        result_code = "ARTIFACT_DELETED"
        try:
            await asyncio.to_thread(
                self.minio.remove_object, command.bucket, command.object_key)
            logger.info(
                "artifact_deleted artifactId=%s bucket=%s objectKey=%s",
                command.artifact_id, command.bucket, command.object_key,
            )
        except Exception:
            status = "FAILED"
            result_code = "ARTIFACT_DELETE_FAILED"
            logger.exception(
                "artifact_delete_failed artifactId=%s bucket=%s",
                command.artifact_id, command.bucket,
            )
        finally:
            reset_correlation_id(correlation_token)
        event_payload = command.model_dump()
        event_payload.update({
            "status": status,
            "result_code": result_code,
            "event_id": uuid5(
                EVENT_NAMESPACE, f"{command.event_id}:artifact-retention"),
            "occurred_at": datetime.now(timezone.utc),
        })
        event = ArtifactRetentionEvent(**event_payload)
        await self._send(self.event_topic, command.execution_id, event)
        self.ledger.complete(command.event_id)
        return True

    @staticmethod
    def _failure(
        command: ExecutionCommand, stage: str, code: str,
        failure: SanitizedFailure | None = None,
    ) -> ExecutionStatusEvent:
        details = (
            failure.model_dump(by_alias=True, mode="json")
            if failure is not None else {"retryable": False}
        )
        return ExecutionStatusEvent(
            schema_version="1.0",
            event_id=uuid5(EVENT_NAMESPACE, f"{command.event_id}:status:{stage}"),
            correlation_id=command.correlation_id, execution_id=command.execution_id,
            entity_id=command.entity_id, actor_user_id=command.actor_user_id,
            occurred_at=datetime.now(timezone.utc), stage=stage,
            status=("CANCELLED" if stage == "CANCELLED"
                    else "TIMED_OUT" if stage == "TIMED_OUT" else "FAILED"),
            progress_percent=100, message_code=code, details=details,
        )

    async def run(self) -> None:
        await self.producer.start()
        await self.consumer.start()
        await self.control_consumer.start()
        logger.info(
            "execution_worker_started commandTopic=%s controlTopic=%s concurrency=%s",
            self.command_topic, self.control_topic,
            os.getenv("SPARK_MAX_CONCURRENT_JOBS", "4"),
        )
        try:
            await asyncio.gather(self._run_commands(), self._run_controls())
        finally:
            logger.info("execution_worker_stopping")
            await self.control_consumer.stop()
            await self.consumer.stop()
            await self.producer.stop()

    async def _run_commands(self) -> None:
        max_records = int(os.getenv("SPARK_MAX_CONCURRENT_JOBS", "4"))
        pending: dict[
            asyncio.Task[bool], tuple[TopicPartition, int, bytes]
        ] = {}
        commit_cursor: dict[TopicPartition, int] = {}
        completed_offsets: dict[TopicPartition, set[int]] = {}
        while True:
            if not self.lifecycle.accepting:
                if pending:
                    await self._complete_command_tasks(
                        pending, commit_cursor, completed_offsets, wait=True)
                    continue
                await asyncio.sleep(0.25)
                continue

            capacity = max_records - len(pending)
            if capacity > 0:
                batches = await self.consumer.getmany(
                    timeout_ms=250, max_records=capacity)
                for topic_partition, messages in batches.items():
                    if messages:
                        commit_cursor.setdefault(topic_partition, messages[0].offset)
                        completed_offsets.setdefault(topic_partition, set())
                    for message in messages:
                        task = asyncio.create_task(self.handle(message.value))
                        pending[task] = (
                            topic_partition, message.offset, message.value)

            if pending:
                await self._complete_command_tasks(
                    pending,
                    commit_cursor,
                    completed_offsets,
                    wait=len(pending) >= max_records,
                )

    async def _complete_command_tasks(
        self,
        pending: dict[asyncio.Task[bool], tuple[TopicPartition, int, bytes]],
        commit_cursor: dict[TopicPartition, int],
        completed_offsets: dict[TopicPartition, set[int]],
        *,
        wait: bool,
    ) -> None:
        done, _ = await asyncio.wait(
            pending,
            timeout=None if wait else 0,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            topic_partition, offset, value = pending.pop(task)
            try:
                completed = task.result()
            except Exception:
                logger.exception(
                    "execution_dispatch_failed partition=%s offset=%s",
                    topic_partition.partition,
                    offset,
                )
                completed = False
            if completed:
                completed_offsets[topic_partition].add(offset)
            elif self.lifecycle.accepting:
                retry = asyncio.create_task(self._retry_command(value))
                pending[retry] = (topic_partition, offset, value)

        commits: dict[TopicPartition, OffsetAndMetadata] = {}
        for topic_partition, offsets in completed_offsets.items():
            cursor = commit_cursor[topic_partition]
            previous = cursor
            while cursor in offsets:
                offsets.remove(cursor)
                cursor += 1
            if cursor > previous:
                commit_cursor[topic_partition] = cursor
                commits[topic_partition] = OffsetAndMetadata(cursor, "")
        if commits:
            await self.consumer.commit(commits)

    async def _retry_command(self, value: bytes) -> bool:
        await asyncio.sleep(0.25)
        return await self.handle(value)

    async def _run_controls(self) -> None:
        async for message in self.control_consumer:
            if await self.handle_control(message.value):
                await self.control_consumer.commit()


def main() -> None:
    asyncio.run(KafkaExecutionWorker().run())
