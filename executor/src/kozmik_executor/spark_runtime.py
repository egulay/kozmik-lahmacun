import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

logger = logging.getLogger(__name__)
P = ParamSpec("P")
T = TypeVar("T")

def run_spark_operation(
    operation: str, function: Callable[P, T], *args: P.args, **kwargs: P.kwargs,
) -> T:
    """Submit an independent driver operation to Spark's FAIR scheduler."""
    logger.debug("spark_operation_started operation=%s", operation)
    try:
        return function(*args, **kwargs)
    finally:
        logger.debug("spark_operation_completed operation=%s", operation)
