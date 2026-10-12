import asyncio
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any, Self
from uuid import uuid4

import pytest

from spectra_inspector_server import main
from spectra_inspector_server._testing import _on_disc_mock
from spectra_inspector_server.main import (
    _pending,
    _results,
    process_requests,
    queueOpsItem,
    submit_op,
)


class _InlinePool:
    """Stands in for the ``ProcessPoolExecutor``: runs each submission in the
    calling thread and remembers the items it was handed."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.submitted: list[queueOpsItem] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def submit(self, fn: Callable[..., Any], *args: Any) -> Future[Any]:
        self.submitted.append(args[-1])
        fut: Future[Any] = Future()
        fut.set_result(fn(*args))
        return fut


def _item() -> queueOpsItem:
    return queueOpsItem(
        ops_func="get_spectrum",
        ops_id=uuid4().hex,
        ops_args=(_on_disc_mock.filenames[0],),
    )


def test_orphaned_items_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    handled: list[str] = []

    def fake_handler(_ph: object, item: queueOpsItem) -> None:
        handled.append(item.ops_id)

    pools: list[_InlinePool] = []

    def make_pool(*args: Any, **kwargs: Any) -> _InlinePool:
        pool = _InlinePool(*args, **kwargs)
        pools.append(pool)
        return pool

    monkeypatch.setattr(main, "ProcessPoolExecutor", make_pool)
    monkeypatch.setattr(main, "process_handler", fake_handler)

    async def scenario() -> None:
        q: asyncio.Queue[queueOpsItem] = asyncio.Queue()
        orphan = _item()
        await submit_op(q, orphan)
        # the client gave up (timed out) before the consumer reached its item
        _pending.pop(orphan.ops_id)

        live = _item()
        await submit_op(q, live)
        live_done = _pending[live.ops_id]

        consumer = asyncio.create_task(process_requests(q, ph=None))  # type: ignore[arg-type]
        try:
            await asyncio.wait_for(live_done.wait(), timeout=5)
            await q.join()
        finally:
            consumer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await consumer

        assert handled == [live.ops_id]
        assert [i.ops_id for i in pools[0].submitted] == [live.ops_id]
        assert live.ops_id in _results
        assert orphan.ops_id not in _results
        _results.pop(live.ops_id)
        _pending.pop(live.ops_id, None)

    asyncio.run(scenario())
