import asyncio
import logging
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from kozmik_executor.chat.api import (
    _authenticate,
    configuration_client,
    provider_registry,
    router as chat_router,
)
from kozmik_executor.chat.providers import ProviderError
from kozmik_executor.execution.worker import KafkaExecutionWorker
from kozmik_executor.ingestion.worker import KafkaIngestionWorker
from kozmik_executor.ingestion.stream import KafkaStreamIngestionWorker
from kozmik_executor.planning.api import router as planning_router
from kozmik_executor.logging_config import reset_correlation_id, set_correlation_id
from kozmik_executor.artifacts import router as artifact_router
from kozmik_executor.secrets import VaultSecretError, load_runtime_secrets_from_vault

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Spark Python workers must use the same governed environment as the API/worker
    # process. In particular, Spark XGBoost requires pandas and pyarrow there.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    try:
        await load_runtime_secrets_from_vault()
        # A fresh process reloads Java-owned effective configuration only after
        # its internal credential has been obtained from Vault.
        app.state.effective_configuration = await configuration_client.load()
        provider = provider_registry.resolve(app.state.effective_configuration.llm)
        ensure_ready = getattr(provider, "ensure_ready", None)
        if ensure_ready is not None:
            await ensure_ready()
        elif not await provider.health():
            raise ProviderError("LLM_PROVIDER_UNAVAILABLE")
    except (ProviderError, VaultSecretError) as exception:
        logger.critical("Executor startup stopped: %s", exception)
        raise RuntimeError(str(exception)) from exception
    execution_configuration = app.state.effective_configuration.execution or {}
    configured_concurrency = execution_configuration.get("maxConcurrentJobs")
    if configured_concurrency is not None:
        os.environ["SPARK_MAX_CONCURRENT_JOBS"] = str(configured_concurrency)
    worker_tasks: list[asyncio.Task] = []
    if os.getenv("EXECUTION_WORKER_ENABLED", "false").lower() == "true":
        worker_tasks.append(asyncio.create_task(
            KafkaExecutionWorker().run(), name="execution-worker"))
    if os.getenv("INGESTION_WORKER_ENABLED", "false").lower() == "true":
        worker_tasks.append(asyncio.create_task(
            KafkaIngestionWorker().run(), name="ingestion-worker"))
    if os.getenv("STREAM_INGESTION_WORKER_ENABLED", "false").lower() == "true":
        worker_tasks.append(asyncio.create_task(
            KafkaStreamIngestionWorker().run(), name="stream-ingestion-worker"))
    try:
        yield
    finally:
        for worker_task in worker_tasks:
            worker_task.cancel()
        if worker_tasks:
            await asyncio.gather(*worker_tasks, return_exceptions=True)


app = FastAPI(
    title="Kozmik Executor",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.include_router(chat_router)
app.include_router(planning_router)
app.include_router(artifact_router)


@app.exception_handler(StarletteHTTPException)
async def handled_http_exception(request: Request, exception: StarletteHTTPException):
    logger.warning(
        "http_request_rejected method=%s path=%s status=%s",
        request.method, request.url.path, exception.status_code,
    )
    return await http_exception_handler(request, exception)


@app.exception_handler(RequestValidationError)
async def request_validation_exception(request: Request, exception: RequestValidationError):
    safe_errors = [
        {
            "location": ".".join(str(part) for part in error.get("loc", ())),
            "type": error.get("type", "validation_error"),
            "message": error.get("msg", "invalid value"),
        }
        for error in exception.errors()
    ]
    logger.warning(
        "http_request_validation_failed method=%s path=%s errors=%s details=%s",
        request.method, request.url.path, len(safe_errors), safe_errors,
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exception.errors()},
    )


@app.exception_handler(Exception)
async def unexpected_exception(request: Request, exception: Exception):
    logger.exception(
        "http_request_failed method=%s path=%s code=INTERNAL_ERROR",
        request.method, request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "INTERNAL_ERROR",
                            "message": "An unexpected error occurred"}},
    )


@app.middleware("http")
async def correlation_context(request: Request, call_next):
    supplied = request.headers.get("X-Correlation-ID", "")
    value = supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,100}", supplied) else str(uuid.uuid4())
    token = set_correlation_id(value)
    started = time.monotonic()
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = value
        logger.info(
            "http_request_completed method=%s path=%s status=%s durationMs=%s",
            request.method, request.url.path, response.status_code,
            round((time.monotonic() - started) * 1000),
        )
        return response
    finally:
        reset_correlation_id(token)


@app.get("/internal/v1/health")
async def health(x_internal_api_key: str | None = Header(default=None)) -> dict[str, str]:
    """Expose sanitized Python and selected-provider health."""
    _authenticate(x_internal_api_key)
    try:
        effective = await configuration_client.load()
        provider = provider_registry.resolve(effective.llm)
        available = await provider.health()
        return {
            "status": "AVAILABLE",
            "providerStatus": "AVAILABLE" if available else "UNAVAILABLE",
            "provider": provider.name,
        }
    except ProviderError:
        return {"status": "DEGRADED", "providerStatus": "UNKNOWN", "provider": "unknown"}


@app.get("/internal/v1/liveness")
async def liveness() -> dict[str, str]:
    """Expose process liveness without credentials or dependency details."""
    return {"status": "UP"}
