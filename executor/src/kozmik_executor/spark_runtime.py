import logging
import threading
from collections.abc import Callable
from typing import ParamSpec, TypeVar

logger = logging.getLogger(__name__)
P = ParamSpec("P")
T = TypeVar("T")

# Local ingestion and execution workers share one SparkContext. Spark itself
# parallelizes each operation; submitting unrelated driver operations from
# multiple Python threads can destabilize the local JVM, especially during
# model tuning. Keep driver operations serialized while preserving Spark's
# internal task parallelism.
_DRIVER_GATE = threading.RLock()


def run_spark_operation(
    operation: str, function: Callable[P, T], *args: P.args, **kwargs: P.kwargs,
) -> T:
    logger.debug("spark_operation_waiting operation=%s", operation)
    with _DRIVER_GATE:
        logger.debug("spark_operation_started operation=%s", operation)
        try:
            return function(*args, **kwargs)
        finally:
            logger.debug("spark_operation_completed operation=%s", operation)
