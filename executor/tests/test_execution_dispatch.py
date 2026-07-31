import asyncio
from types import SimpleNamespace

from aiokafka.structs import TopicPartition

from kozmik_executor.execution.worker import KafkaExecutionWorker


def test_command_consumer_refills_capacity_before_first_job_finishes(monkeypatch) -> None:
    monkeypatch.setenv("SPARK_MAX_CONCURRENT_JOBS", "2")

    async def scenario() -> tuple[int, list[dict]]:
        partition = TopicPartition("execution.commands.v1", 0)

        class Consumer:
            def __init__(self) -> None:
                self.polls = 0
                self.commits: list[dict] = []

            async def getmany(self, **_kwargs):
                self.polls += 1
                if self.polls == 1:
                    return {partition: [SimpleNamespace(offset=0, value=b"first")]}
                if self.polls == 2:
                    return {partition: [SimpleNamespace(offset=1, value=b"second")]}
                await asyncio.sleep(0.01)
                return {}

            async def commit(self, offsets):
                self.commits.append(offsets)

        consumer = Consumer()
        worker = KafkaExecutionWorker.__new__(KafkaExecutionWorker)
        worker.consumer = consumer
        worker.lifecycle = SimpleNamespace(accepting=True)
        release = asyncio.Event()
        second_started = asyncio.Event()
        active = 0
        peak = 0

        async def handle(value: bytes) -> bool:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if value == b"second":
                second_started.set()
            await release.wait()
            active -= 1
            return True

        worker.handle = handle
        dispatcher = asyncio.create_task(worker._run_commands())
        await asyncio.wait_for(second_started.wait(), timeout=1)
        release.set()
        while not consumer.commits:
            await asyncio.sleep(0.01)
        dispatcher.cancel()
        try:
            await dispatcher
        except asyncio.CancelledError:
            pass
        return peak, consumer.commits

    peak, commits = asyncio.run(scenario())

    assert peak == 2
    assert list(commits[-1].values())[0].offset == 2
