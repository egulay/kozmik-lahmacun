import pytest

from kozmik_executor.spark_session import spark_configuration


def test_default_spark_configuration_uses_safe_resource_bounds(monkeypatch) -> None:
    for name in (
        "SPARK_MASTER", "SPARK_EXECUTOR_MEMORY", "SPARK_EXECUTOR_CORES",
        "SPARK_EXECUTOR_INSTANCES", "SPARK_DYNAMIC_ALLOCATION_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    configuration = spark_configuration()

    assert configuration.master is None
    assert configuration.spark_config["spark.executor.memory"] == "4g"
    assert configuration.spark_config["spark.executor.cores"] == "2"
    assert configuration.spark_config["spark.executor.instances"] == "2"
    assert configuration.spark_config["spark.driver.maxResultSize"] == "512m"
    assert configuration.enable_hive_support is False


def test_cluster_master_and_dynamic_allocation_are_configurable(monkeypatch) -> None:
    monkeypatch.setenv("SPARK_MASTER", "spark://spark-master.internal:7077")
    monkeypatch.setenv("SPARK_DYNAMIC_ALLOCATION_ENABLED", "true")
    monkeypatch.setenv("SPARK_DYNAMIC_ALLOCATION_MIN_EXECUTORS", "2")
    monkeypatch.setenv("SPARK_DYNAMIC_ALLOCATION_INITIAL_EXECUTORS", "4")
    monkeypatch.setenv("SPARK_DYNAMIC_ALLOCATION_MAX_EXECUTORS", "12")

    configuration = spark_configuration()

    assert configuration.master == "spark://spark-master.internal:7077"
    assert configuration.spark_config["spark.dynamicAllocation.enabled"] == "true"
    assert configuration.spark_config["spark.dynamicAllocation.maxExecutors"] == "12"
    assert "spark.executor.instances" not in configuration.spark_config


def test_invalid_dynamic_allocation_range_fails_at_startup(monkeypatch) -> None:
    monkeypatch.setenv("SPARK_DYNAMIC_ALLOCATION_ENABLED", "true")
    monkeypatch.setenv("SPARK_DYNAMIC_ALLOCATION_MIN_EXECUTORS", "5")
    monkeypatch.setenv("SPARK_DYNAMIC_ALLOCATION_INITIAL_EXECUTORS", "2")
    monkeypatch.setenv("SPARK_DYNAMIC_ALLOCATION_MAX_EXECUTORS", "3")

    with pytest.raises(ValueError, match="min <= initial <= max"):
        spark_configuration()
