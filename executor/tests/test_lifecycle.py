import asyncio
from uuid import uuid4

from kozmik_executor.lifecycle import LifecycleCoordinator


def test_cooperative_execution_cancellation():
    async def scenario():
        coordinator = LifecycleCoordinator()
        cancelled = asyncio.Event()
        spark_cancelled = []
        execution_id = uuid4()
        assert await coordinator.register(
            execution_id, cancelled, lambda: spark_cancelled.append(execution_id)
        )
        assert await coordinator.cancel(execution_id)
        assert cancelled.is_set()
        assert spark_cancelled == [execution_id]
        await coordinator.complete(execution_id)
    asyncio.run(scenario())


def test_cancellation_received_before_registration_is_not_lost():
    async def scenario():
        coordinator = LifecycleCoordinator()
        execution_id = uuid4()
        cancelled = asyncio.Event()
        spark_cancelled = []

        assert await coordinator.cancel(execution_id)
        assert await coordinator.register(
            execution_id, cancelled, lambda: spark_cancelled.append(execution_id)
        )

        assert cancelled.is_set()
        assert spark_cancelled == [execution_id]
        await coordinator.complete(execution_id)
        assert execution_id not in coordinator.pending_cancellations

    asyncio.run(scenario())
