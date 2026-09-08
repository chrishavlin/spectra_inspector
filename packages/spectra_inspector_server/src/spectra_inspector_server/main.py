import asyncio
import threading
from asyncio.tasks import Task
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request

from spectra_inspector_server._file_browser import (
    PathOutsideRootError,
    list_directory,
    relative_to_root,
    resolve_within_root,
)
from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server._testing import pytest_running
from spectra_inspector_server._typing import LifespanGenerator, OptionalOpsReturnType
from spectra_inspector_server.dependencies import get_database_session, get_settings
from spectra_inspector_server.model import (
    AvailableDatasets,
    CombinedMetadata,
    Info,
    MetadataModel,
    Spectrum1d,
    Spectrum1dDict,
    directoryListing,
    raveledImage,
    sampleMetadata,
)
from spectra_inspector_server.processor.operations import OperationEDAXStateHandler
from spectra_inspector_server.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Container


def _valid_sample_name(
    sample_name: str, ph: EDAXPathHandler, spectrum_only: bool = False
) -> bool:
    """Whether ``sample_name`` can be served: as a ``.spc`` spectrum when
    ``spectrum_only`` is set, otherwise as a map."""
    known: Container[str]
    if spectrum_only:
        known = ph.database.available_spectra
    else:
        known = ph.database.available_maps
    if sample_name in known:
        return True

    if pytest_running():
        from spectra_inspector_server._testing import _on_disc_mock  # noqa: PLC0415

        return _on_disc_mock.is_mock(sample_name, spectrum_only=spectrum_only)

    return False


_working_directory_lock = threading.Lock()


def _synced_path_handler(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    working_directory: str | None = None,
    working_directory_recursive: bool = True,
) -> EDAXPathHandler:
    """The path handler, rescanned first if the client names a directory this
    worker does not already hold.

    Desktop mode keeps the working directory in a per-process, in-memory
    database, so behind more than one uvicorn worker only the worker that
    served ``/datasets-in-directory`` knows which directory was picked; the
    others answer "not a valid sample" or an empty dataset list. The frontend's
    user store holds the authoritative value, so every request may carry it and
    any worker can catch up on demand.

    Desktop mode serves a single user, which is what makes rescanning on a
    client's say-so safe: there is no other session whose working set this
    would pull out from under them.

    ``working_directory`` is relative to the data root, and "" legitimately
    means the data root itself -- only ``None`` (the frontend has no directory
    committed yet) skips the sync.
    """

    ph = ph_from_app_state(request)

    if working_directory is None or not settings.desktop_mode:
        return ph

    target = _resolve_browse_path(ph, working_directory)
    if ph.database.working_directory == target:
        return ph

    # the frontend fans several requests out at once, and they all carry the
    # same directory; without this the first batch after a switch would each
    # rescan it. Whoever gets here second re-checks and finds the work done.
    with _working_directory_lock:
        if ph.database.working_directory == target:
            return ph

        msg = (
            f"syncing working directory to {target} "
            f"(was {ph.database.working_directory})"
        )
        spectraLogger.info(msg)
        try:
            ph.set_working_directory(target, recursive=working_directory_recursive)
        except NotADirectoryError as err:
            detail = f"'{working_directory}' is not a directory"
            raise HTTPException(404, detail=detail) from err
        except OSError as err:
            detail = f"could not read '{working_directory}'"
            raise HTTPException(403, detail=detail) from err

    return ph


SyncedPathHandler = Annotated[EDAXPathHandler, Depends(_synced_path_handler)]


_results: dict[str, OptionalOpsReturnType] = {}
# one event per queued item, set when its result lands in _results. An ops_id
# missing from here is one nobody is waiting on any more.
_pending: dict[str, asyncio.Event] = {}
_OPS_TIMEOUT_S = 60 * 2
background_tasks: set[Task] = set()  # type:ignore[type-arg]


@dataclass
class queueOpsItem:
    ops_func: str
    ops_id: str
    ops_args: tuple[str] | None | tuple[int, int] | int | str = None
    ops_kwargs: dict[str, None | tuple[int, int] | int | str | tuple[str]] | None = None


def process_handler(ph: EDAXPathHandler, item: queueOpsItem) -> OptionalOpsReturnType:
    ops = OperationEDAXStateHandler(ph, allow_mock_files=pytest_running())
    func = getattr(ops, item.ops_func)
    result = None
    if item.ops_args is None and item.ops_kwargs is None:
        result = func()
    elif item.ops_args is not None and item.ops_kwargs is not None:
        assert isinstance(item.ops_args, tuple)
        result = func(*item.ops_args, **item.ops_kwargs)
    elif item.ops_args is None and item.ops_kwargs is not None:
        result = func(**item.ops_kwargs)
    elif item.ops_args is not None and item.ops_kwargs is None:
        assert isinstance(item.ops_args, tuple)
        result = func(*item.ops_args)
    return result


async def process_requests(q: asyncio.Queue, ph: EDAXPathHandler) -> None:  # type:ignore[type-arg]
    # the worker is kept alive across requests: it caches the memmaps of the
    # filesets it has already opened, and re-mapping a cube is expensive.
    while True:
        with ProcessPoolExecutor(max_workers=1) as pool:
            pool_is_usable = True
            while pool_is_usable:
                item = await q.get()  # Get a request from the queue
                loop = asyncio.get_running_loop()
                r: OptionalOpsReturnType = None
                try:
                    r = await loop.run_in_executor(pool, process_handler, ph, item)
                except BrokenExecutor:
                    spectraLogger.exception("worker process died, restarting it")
                    pool_is_usable = False
                except Exception:  # noqa: BLE001
                    spectraLogger.exception(
                        "%s failed for ops_id %s", item.ops_func, item.ops_id
                    )
                done = _pending.get(item.ops_id)
                if done is None:
                    spectraLogger.warning(
                        "nothing is waiting on ops_id %s, dropping its result",
                        item.ops_id,
                    )
                else:
                    _results[item.ops_id] = r
                    done.set()
                q.task_done()


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> LifespanGenerator:
    q = asyncio.Queue()  # type: ignore[var-annotated]
    ph = get_database_session()

    # start listening to ops requests
    task = asyncio.create_task(process_requests(q, ph))

    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    app.state.ph = ph
    app.state.q = q
    yield {"q": q, "ph": ph}


# configure logger once at startup.
settings = Settings()
spectraLogger.setLevel(settings.log_level.upper())
app = FastAPI(lifespan=lifespan)


@app.get("/info")
async def info(settings: Annotated[Settings, Depends(get_settings)]) -> Info:
    return Info(
        app_name=settings.app_name,
        spectra_inspector_data_root=settings.data_root,
        desktop_mode=settings.desktop_mode,
    )


def _available_datasets_response(ph: EDAXPathHandler) -> AvailableDatasets:
    filekeys = [str(nm) for nm in ph.database.available_maps]

    available_samples = ph.database.available_samples
    all_meta: sampleMetadata | None = None
    if ph.database.sample_metadata_mapper:
        all_meta = ph.database.sample_metadata_mapper.get_all(
            available_samples=available_samples
        )

    directory: str | None = None
    if ph.database.working_directory is not None:
        directory = relative_to_root(ph.data_root, ph.database.working_directory)

    return AvailableDatasets(
        available_files=filekeys,
        sample_metadata=all_meta,
        directory=directory,
        truncated=ph.database.scan_truncated,
        available_spectra=[str(nm) for nm in ph.database.available_spectra],
    )


@app.get("/available-datasets")
async def available_datasets(
    ph: SyncedPathHandler,
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_db: bool = False,
) -> AvailableDatasets:

    if refresh_db:
        if settings.desktop_mode and ph.database.working_directory is None:
            # refreshing before a working directory is picked would mean the
            # full scan of the data root that desktop mode exists to avoid.
            spectraLogger.info("Refresh skipped, no working directory selected.")
        elif settings.allow_db_refresh or settings.desktop_mode:
            # in desktop mode a refresh only re-scans the working directory, so
            # it costs no more than the scan the client already asked for.
            ph.refresh()
        else:
            spectraLogger.info("Refresh attempt denied.")

    return _available_datasets_response(ph)


def _require_desktop_mode(settings: Settings) -> None:
    if not settings.desktop_mode:
        msg = (
            "directory browsing requires the server to run with "
            "SPECTRA_INSPECTOR_DESKTOP_MODE=true"
        )
        raise HTTPException(403, detail=msg)


def _resolve_browse_path(ph: EDAXPathHandler, path: str) -> Path:
    try:
        return resolve_within_root(ph.data_root, path)
    except PathOutsideRootError as err:
        raise HTTPException(403, detail=str(err)) from err


@app.get("/browse-directory")
async def browse_directory(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    path: str = "",
) -> directoryListing:
    """List the subdirectories of one directory beneath the data root."""

    _require_desktop_mode(settings)
    ph = ph_from_app_state(request)

    # validate before listing so that an out-of-root path is a 403 rather than
    # whatever the filesystem happens to say about it.
    _resolve_browse_path(ph, path)

    try:
        return list_directory(
            ph.data_root,
            path,
            allow_mixed_basenames=settings.db_allow_mixed_basenames,
        )
    except NotADirectoryError as err:
        raise HTTPException(404, detail=str(err)) from err
    except OSError as err:
        msg = f"could not read '{path}'"
        raise HTTPException(403, detail=msg) from err


@app.get("/datasets-in-directory")
async def datasets_in_directory(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    path: str = "",
    recursive: bool = True,
) -> AvailableDatasets:
    """Scan one directory beneath the data root and make it the working set.

    Whatever the database held before is replaced, so subsequent data endpoints
    only see the datasets in the selected directory.
    """

    _require_desktop_mode(settings)
    ph = ph_from_app_state(request)

    target = _resolve_browse_path(ph, path)

    try:
        ph.set_working_directory(target, recursive=recursive)
    except NotADirectoryError as err:
        msg = f"'{path}' is not a directory"
        raise HTTPException(404, detail=msg) from err
    except OSError as err:
        msg = f"could not read '{path}'"
        raise HTTPException(403, detail=msg) from err

    return _available_datasets_response(ph)


@app.get("/image-metadata")
async def image_metadata(
    sample_name: str, ph: SyncedPathHandler, spectrum_only: bool = False
) -> MetadataModel:
    """``spectrum_only`` names the sample's ``.spc`` spectrum rather than its
    map, here and on every endpoint that takes it."""

    if not _valid_sample_name(sample_name, ph, spectrum_only=spectrum_only):
        msg = f"{sample_name} is not a valid sample"
        raise HTTPException(404, detail=msg)

    ops = OperationEDAXStateHandler(ph, allow_mock_files=pytest_running())
    return ops.get_refined_metadata(sample_name, spectrum_only=spectrum_only)


async def submit_op(q: asyncio.Queue, item: queueOpsItem) -> None:  # type:ignore[type-arg]
    """Queue an operation, registering interest in its result first."""
    _pending[item.ops_id] = asyncio.Event()
    await q.put(item)


async def await_op_result(item: queueOpsItem) -> OptionalOpsReturnType:
    # the consumer runs in this loop too, so waiting on an event hands the
    # result over as soon as it exists rather than on the next poll.
    done = _pending[item.ops_id]
    try:
        await asyncio.wait_for(done.wait(), timeout=_OPS_TIMEOUT_S)
    except TimeoutError:
        msg = f"timeout error after {_OPS_TIMEOUT_S} s"
        raise TimeoutError(msg) from None
    finally:
        _pending.pop(item.ops_id, None)
    result = _results.pop(item.ops_id)
    assert item.ops_id not in _results
    return result


@app.get("/image-metadata-combined")
async def image_metadata_combined(
    sample_name: str, ph: SyncedPathHandler, spectrum_only: bool = False
) -> CombinedMetadata:

    if not _valid_sample_name(sample_name, ph, spectrum_only=spectrum_only):
        msg = f"{sample_name} is not a valid sample"
        raise HTTPException(404, detail=msg)

    ops = OperationEDAXStateHandler(ph, allow_mock_files=pytest_running())
    return ops.get_combined_metadata(sample_name, spectrum_only=spectrum_only)


@app.get("/image-spectrum")
async def image_spectrum(
    sample_name: str,
    request: Request,
    ph: SyncedPathHandler,
    channel_0: int | None = None,
    channel_1: int | None = None,
    index0_0: int | None | Literal["none"] = None,
    index0_1: int | None | Literal["none"] = None,
    index1_0: int | None | Literal["none"] = None,
    index1_1: int | None | Literal["none"] = None,
    include_weights: bool = True,
    spectrum_only: bool = False,
) -> Spectrum1dDict:

    if not _valid_sample_name(sample_name, ph, spectrum_only=spectrum_only):
        msg = f"{sample_name} is not a valid sample"
        raise HTTPException(404, detail=msg)

    q = request.app.state.q
    assert isinstance(q, asyncio.Queue)

    index0_range: None | tuple[int, int]
    if isinstance(index0_0, int) and isinstance(index0_1, int):
        index0_range = (int(index0_0), int(index0_1))
    else:
        index0_range = None

    index1_range: None | tuple[int, int]
    if isinstance(index1_0, int) and isinstance(index1_1, int):
        index1_range = (int(index1_0), int(index1_1))
    else:
        index1_range = None

    channel_range: None | tuple[int, int]
    if isinstance(channel_0, int) and isinstance(channel_1, int):
        channel_range = (int(channel_0), int(channel_1))
    else:
        channel_range = None

    item = queueOpsItem(
        ops_func="get_spectrum",
        ops_id=uuid4().hex,
        ops_args=(sample_name,),
        ops_kwargs={
            "channel_range": channel_range,
            "index0_range": index0_range,
            "index1_range": index1_range,
            "spectrum_only": spectrum_only,
        },
    )

    await submit_op(q, item)
    result = None
    try:
        result = await await_op_result(item)
    except TimeoutError as err:
        msg = "Timeout error during spectrum calculation"
        raise HTTPException(404, detail=msg) from err

    assert isinstance(result, Spectrum1d)

    res = result.todict(include_weights=include_weights)  # type:ignore[unreachable]
    return res


@app.get("/image-data")
async def image_data(
    sample_name: str,
    channel_index: int,
    request: Request,
    ph: SyncedPathHandler,
    index0_0: int | None | Literal["none"] = None,
    index0_1: int | None | Literal["none"] = None,
    index1_0: int | None | Literal["none"] = None,
    index1_1: int | None | Literal["none"] = None,
) -> raveledImage:

    if not _valid_sample_name(sample_name, ph):
        msg = f"{sample_name} is not a valid sample"
        raise HTTPException(404, detail=msg)

    index0_range: None | tuple[int, int]
    if isinstance(index0_0, int) and isinstance(index0_1, int):
        index0_range = (int(index0_0), int(index0_1))
    else:
        index0_range = None

    index1_range: None | tuple[int, int]
    if isinstance(index1_0, int) and isinstance(index1_1, int):
        index1_range = (int(index1_0), int(index1_1))
    else:
        index1_range = None

    item = queueOpsItem(
        ops_func="get_single_image",
        ops_id=uuid4().hex,
        ops_args=(sample_name,),
        ops_kwargs={
            "channel_index": channel_index,
            "index0_range": index0_range,
            "index1_range": index1_range,
        },
    )

    await submit_op(request.app.state.q, item)
    try:
        result = await await_op_result(item)
    except TimeoutError as err:
        msg = "Timeout error during get_single_image call"
        raise HTTPException(404, detail=msg) from err

    assert isinstance(result, raveledImage)
    return result


def ph_from_app_state(request: Request) -> EDAXPathHandler:
    if hasattr(request.app.state, "ph"):
        ph = request.app.state.ph
        assert isinstance(ph, EDAXPathHandler)
        return ph
    return get_database_session()


@app.get("/image-data-summed")
async def image_data_summed(
    sample_name: str,
    channel_0: int,
    channel_1: int,
    request: Request,
    ph: SyncedPathHandler,
    index0_0: int | None | Literal["none"] = None,
    index0_1: int | None | Literal["none"] = None,
    index1_0: int | None | Literal["none"] = None,
    index1_1: int | None | Literal["none"] = None,
) -> raveledImage:

    if not _valid_sample_name(sample_name, ph):
        msg = f"{sample_name} is not a valid sample"
        raise HTTPException(404, detail=msg)

    index0_range: None | tuple[int, int]
    if isinstance(index0_0, int) and isinstance(index0_1, int):
        index0_range = (int(index0_0), int(index0_1))
    else:
        index0_range = None

    index1_range: None | tuple[int, int]
    if isinstance(index1_0, int) and isinstance(index1_1, int):
        index1_range = (int(index1_0), int(index1_1))
    else:
        index1_range = None

    channel_range = (channel_0, channel_1)
    msg = f"fetching summed channel intensity for {sample_name} with {channel_range=}, {index0_range=}, {index1_range=}"
    spectraLogger.info(msg)

    item = queueOpsItem(
        ops_func="get_raveled_multi_channel_intensity_image",
        ops_id=uuid4().hex,
        ops_args=(sample_name,),
        ops_kwargs={
            "channel_range": channel_range,
            "index0_range": index0_range,
            "index1_range": index1_range,
        },
    )

    await submit_op(request.app.state.q, item)
    try:
        result = await await_op_result(item)
    except TimeoutError as err:
        msg = "Timeout error during get_raveled_multi_channel_intensity_image call"
        raise HTTPException(404, detail=msg) from err

    assert isinstance(result, raveledImage)
    return result
