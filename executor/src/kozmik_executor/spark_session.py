import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pyspark.sql import SparkSession


_MEMORY_PATTERN = re.compile(r"^[1-9][0-9]*(?:[kKmMgGtT])$")
_ENVIRONMENT_OVERRIDES = {
    "SPARK_SCHEDULER_MODE": "spark.scheduler.mode",
    "SPARK_DRIVER_MAX_RESULT_SIZE": "spark.driver.maxResultSize",
    "SPARK_EXECUTOR_MEMORY": "spark.executor.memory",
    "SPARK_EXECUTOR_CORES": "spark.executor.cores",
    "SPARK_EXECUTOR_INSTANCES": "spark.executor.instances",
    "SPARK_SQL_SHUFFLE_PARTITIONS": "spark.sql.shuffle.partitions",
    "SPARK_DYNAMIC_ALLOCATION_ENABLED": "spark.dynamicAllocation.enabled",
    "SPARK_DYNAMIC_ALLOCATION_MIN_EXECUTORS": "spark.dynamicAllocation.minExecutors",
    "SPARK_DYNAMIC_ALLOCATION_INITIAL_EXECUTORS": "spark.dynamicAllocation.initialExecutors",
    "SPARK_DYNAMIC_ALLOCATION_MAX_EXECUTORS": "spark.dynamicAllocation.maxExecutors",
}


@dataclass(frozen=True)
class SparkRuntimeConfiguration:
    master: str | None
    spark_config: dict[str, str]
    enable_hive_support: bool


def _configuration_path() -> Path:
    configured = os.getenv("SPARK_CONFIG_FILE", "").strip()
    return Path(configured) if configured else Path(__file__).parents[2] / "config/spark.yml"


def _scalar(value: object, key: str) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (str, int, float)) and not isinstance(value, complex):
        return str(value)
    raise ValueError(f"Spark configuration {key} must have a scalar value")


def _validate(settings: dict[str, str]) -> None:
    if len(settings) > 200:
        raise ValueError("spark_config cannot contain more than 200 properties")
    for key, value in settings.items():
        if not key.startswith("spark.") or len(key) > 200:
            raise ValueError(f"Invalid Spark configuration key: {key}")
        if not value or len(value) > 2000:
            raise ValueError(f"Invalid Spark configuration value for {key}")

    for key in ("spark.driver.maxResultSize", "spark.executor.memory"):
        value = settings.get(key)
        if value is not None and not _MEMORY_PATTERN.fullmatch(value):
            raise ValueError(f"{key} must use a Spark memory value such as 4g or 512m")
    for key in (
        "spark.executor.cores", "spark.executor.instances",
        "spark.sql.shuffle.partitions", "spark.dynamicAllocation.minExecutors",
        "spark.dynamicAllocation.initialExecutors", "spark.dynamicAllocation.maxExecutors",
    ):
        value = settings.get(key)
        if value is not None and (not value.isdigit() or int(value) < 1):
            raise ValueError(f"{key} must be a positive integer")

    dynamic = settings.get("spark.dynamicAllocation.enabled", "false").lower()
    if dynamic not in {"true", "false"}:
        raise ValueError("spark.dynamicAllocation.enabled must be true or false")
    if dynamic == "true":
        minimum = int(settings.get("spark.dynamicAllocation.minExecutors", "1"))
        initial = int(settings.get("spark.dynamicAllocation.initialExecutors", "1"))
        maximum = int(settings.get("spark.dynamicAllocation.maxExecutors", "1"))
        if not minimum <= initial <= maximum:
            raise ValueError("Spark dynamic allocation must satisfy min <= initial <= max")
        settings.pop("spark.executor.instances", None)


def spark_configuration() -> SparkRuntimeConfiguration:
    """Load operator-owned Spark configuration; execution orders cannot reach this path."""
    path = _configuration_path()
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exception:
        raise ValueError(f"Unable to load Spark configuration from {path}") from exception
    if not isinstance(document, dict):
        raise ValueError("Spark configuration root must be a mapping")
    raw_settings = document.get("spark_config", {})
    if not isinstance(raw_settings, dict):
        raise ValueError("spark_config must be a mapping")
    settings = {_scalar(key, "key"): _scalar(value, str(key))
                for key, value in raw_settings.items()}
    for environment_name, spark_key in _ENVIRONMENT_OVERRIDES.items():
        value = os.getenv(environment_name, "").strip()
        if value:
            settings[spark_key] = value
    _validate(settings)

    master_override = os.getenv("SPARK_MASTER", "").strip()
    configured_master = document.get("master")
    master = master_override or (
        _scalar(configured_master, "master").strip()
        if configured_master is not None else ""
    )
    hive = document.get("enable_hive_support", False)
    if not isinstance(hive, bool):
        raise ValueError("enable_hive_support must be true or false")
    return SparkRuntimeConfiguration(master or None, settings, hive)


def build_spark_session(application_name: str) -> SparkSession:
    """Create a local or cluster-backed session from operator-owned configuration."""
    configuration = spark_configuration()
    builder = SparkSession.builder.appName(application_name)
    if configuration.master is not None:
        builder = builder.master(configuration.master)
    for key, value in configuration.spark_config.items():
        builder = builder.config(key, value)
    if configuration.enable_hive_support:
        builder = builder.enableHiveSupport()
    return builder.getOrCreate()
