import threading
import time
from concurrent.futures import ThreadPoolExecutor

from kozmik_executor.spark_runtime import run_spark_operation


def test_independent_spark_driver_operations_are_not_process_serialized() -> None:
    barrier = threading.Barrier(2)
    state_lock = threading.Lock()
    active = 0
    peak = 0

    def operation() -> None:
        nonlocal active, peak
        barrier.wait(timeout=1)
        with state_lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with state_lock:
            active -= 1

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run_spark_operation, f"operation-{index}", operation)
            for index in range(2)
        ]
        for future in futures:
            future.result(timeout=2)

    assert peak == 2
