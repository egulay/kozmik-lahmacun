"""Canonical Spark DataFrame-to-MinIO Parquet artifact writer."""

import tempfile
from pathlib import Path


def write_parquet_artifact(frame, minio, bucket: str, object_key: str) -> int:
    with tempfile.TemporaryDirectory(prefix="kozmik-parquet-") as directory:
        output = Path(directory) / "dataset"
        frame.coalesce(1).write.mode("overwrite").parquet(str(output))
        part = next(output.glob("part-*.parquet"))
        minio.fput_object(bucket, object_key, str(part))
        return part.stat().st_size
