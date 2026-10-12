import asyncio
from collections.abc import Callable, Generator
from concurrent.futures import Future
from typing import Any, Self
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from spectra_inspector_server import main
from spectra_inspector_server._testing import _on_disc_mock
from spectra_inspector_server.dependencies import get_database_session, get_settings
from spectra_inspector_server.main import (
    _pending,
    _results,
    app,
    process_requests,
    queueOpsItem,
    submit_op,
)
from spectra_inspector_server.settings import ENV_PREFIX


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


def test_a_full_queue_refuses_the_next_item() -> None:
    async def scenario() -> None:
        q: asyncio.Queue[queueOpsItem] = asyncio.Queue(maxsize=2)
        queued = [_item(), _item()]
        for item in queued:
            await submit_op(q, item)
        assert q.full()

        refused = _item()
        with pytest.raises(HTTPException) as excinfo:
            await submit_op(q, refused)
        assert excinfo.value.status_code == 503
        assert excinfo.value.headers == {"Retry-After": str(main._RETRY_AFTER_S)}
        # nothing waits on a refused item, and the queue is as it was
        assert refused.ops_id not in _pending
        assert q.qsize() == 2
        for item in queued:
            _pending.pop(item.ops_id)

    asyncio.run(scenario())


@pytest.fixture
def stalled_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """The app with room for two queued ops, a consumer that never takes
    one, and a timeout short enough to wait out."""

    async def stalled(_q: asyncio.Queue[queueOpsItem], _ph: object) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "process_requests", stalled)
    monkeypatch.setattr(main, "_OPS_TIMEOUT_S", 0.2)
    monkeypatch.setenv(f"{ENV_PREFIX}MAX_QUEUED_OPS", "2")
    get_settings.cache_clear()
    get_database_session.cache_clear()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        get_settings.cache_clear()
        get_database_session.cache_clear()


def test_busy_server_answers_504_then_503(stalled_client: TestClient) -> None:
    params: dict[str, str | bool] = {
        "sample_name": _on_disc_mock.filenames[0],
        "include_weights": False,
    }

    # the queue fills up with items the worker never reaches
    for _ in range(2):
        response = stalled_client.get("/image-spectrum", params=params)
        assert response.status_code == 504
        assert "timed out" in response.json()["detail"]

    response = stalled_client.get("/image-spectrum", params=params)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == str(main._RETRY_AFTER_S)
    assert "busy" in response.json()["detail"]
    assert not _pending
