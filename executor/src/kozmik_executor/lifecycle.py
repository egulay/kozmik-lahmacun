import asyncio
from collections.abc import Callable
from uuid import UUID

class LifecycleCoordinator:
    def __init__(self) -> None:
        self.accepting = True
        self.active: dict[UUID, tuple[asyncio.Event, Callable[[], None]]] = {}
        self.pending_cancellations: set[UUID] = set()
        self.changed = asyncio.Condition()

    async def register(
        self, execution_id: UUID, event: asyncio.Event, cancel_spark: Callable[[], None]
    ) -> bool:
        async with self.changed:
            if not self.accepting:
                return False
            self.active[execution_id] = (event, cancel_spark)
            if execution_id in self.pending_cancellations:
                event.set()
                cancel_spark()
            return True

    async def complete(self, execution_id: UUID) -> None:
        async with self.changed:
            self.active.pop(execution_id, None)
            self.pending_cancellations.discard(execution_id)
            self.changed.notify_all()

    async def cancel(self, execution_id: UUID) -> bool:
        async with self.changed:
            target = self.active.get(execution_id)
            if target is None:
                self.pending_cancellations.add(execution_id)
                return True
            target[0].set()
            target[1]()
            return True

lifecycle_coordinator = LifecycleCoordinator()
