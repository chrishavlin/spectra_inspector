import asyncio
from asyncio.tasks import Task
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal
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


def _valid_sample_name(sample_name: str, ph: EDAXPathHandler) -> bool:
    if sample_name in ph.database.available_maps:
        return True

    if pytest_running():
        from spectra_inspector_server._testing import _on_disc_mock  # noqa: PLC0415

        return sample_name in _on_disc_mock.filenames

    return False


_results: dict[str, OptionalOpsReturnType] = {}
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
    while True:
        with ProcessPoolExecutor() as pool:
            item = await q.get()  # Get a request from the queue
            loop = asyncio.get_running_loop()
            r = await loop.run_in_executor(pool, process_handler, ph, item)
            _results[item.ops_id] = r
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
    )


@app.get("/available-datasets")
async def available_datasets(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_db: bool = False,
) -> AvailableDatasets:

    ph = ph_from_app_state(request)

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
async def image_metadata(sample_name: str, request: Request) -> MetadataModel:

    ph = ph_from_app_state(request)

    if not _valid_sample_name(sample_name, ph):
        msg = f"{sample_name} is not a valid sample"
        raise HTTPException(404, detail=msg)

    ops = OperationEDAXStateHandler(ph, allow_mock_files=pytest_running())
    return ops.get_refined_metadata(sample_name)


async def await_op_result(item: queueOpsItem) -> OptionalOpsReturnType:
    total_time = 0.0
    dt = 0.01
    timeout = 60 * 2
    while True:
        if item.ops_id not in _results:
            await asyncio.sleep(dt)
            total_time += dt
        elif total_time > timeout:
            msg = f"timeout error after {total_time} s"
            raise TimeoutError(msg)
        else:
            break
    result = _results.pop(item.ops_id)
    assert item.ops_id not in _results
    return result


@app.get("/image-metadata-combined")
async def image_metadata_combined(
    sample_name: str, request: Request
) -> CombinedMetadata:

    ph = ph_from_app_state(request)

    if not _valid_sample_name(sample_name, ph):
        msg = f"{sample_name} is not a valid sample"
        raise HTTPException(404, detail=msg)

    ops = OperationEDAXStateHandler(ph, allow_mock_files=pytest_running())
    return ops.get_combined_metadata(sample_name)


@app.get("/image-spectrum")
async def image_spectrum(
    sample_name: str,
    request: Request,
    channel_0: int | None = None,
    channel_1: int | None = None,
    index0_0: int | None | Literal["none"] = None,
    index0_1: int | None | Literal["none"] = None,
    index1_0: int | None | Literal["none"] = None,
    index1_1: int | None | Literal["none"] = None,
    include_weights: bool = True,
) -> Spectrum1dDict:

    ph = ph_from_app_state(request)
    if not _valid_sample_name(sample_name, ph):
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
        },
    )

    await q.put(item)
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
    index0_0: int | None | Literal["none"] = None,
    index0_1: int | None | Literal["none"] = None,
    index1_0: int | None | Literal["none"] = None,
    index1_1: int | None | Literal["none"] = None,
) -> raveledImage:

    ph = ph_from_app_state(request)

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

    await request.app.state.q.put(item)
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
    index0_0: int | None | Literal["none"] = None,
    index0_1: int | None | Literal["none"] = None,
    index1_0: int | None | Literal["none"] = None,
    index1_1: int | None | Literal["none"] = None,
) -> raveledImage:

    ph = ph_from_app_state(request)
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

    await request.app.state.q.put(item)
    try:
        result = await await_op_result(item)
    except TimeoutError as err:
        msg = "Timeout error during get_raveled_multi_channel_intensity_image call"
        raise HTTPException(404, detail=msg) from err

    assert isinstance(result, raveledImage)
    return result
