import asyncio
from asyncio.tasks import Task
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request

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
    raveledImage,
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
        result = func(*item.ops_args, **item.ops_kwargs)
    elif item.ops_args is None and item.ops_kwargs is not None:
        result = func(**item.ops_kwargs)
    elif item.ops_args is not None and item.ops_kwargs is None:
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


app = FastAPI(lifespan=lifespan)


@app.get("/info")
async def info(settings: Annotated[Settings, Depends(get_settings)]) -> Info:
    return Info(
        app_name=settings.app_name,
        spectra_inspector_data_root=settings.spectra_inspector_data_root,
    )


@app.get("/available-datasets")
async def available_datasets(request: Request) -> AvailableDatasets:

    ph = ph_from_app_state(request)
    filekeys = [str(nm) for nm in ph.database.available_maps]

    available_samples = ph.database.available_samples
    all_meta = ph.database.sample_metadata_mapper.get_all(
        available_samples=available_samples
    )
    return AvailableDatasets(available_files=filekeys, sample_metadata=all_meta)


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
    return result.todict()  # type:ignore[unreachable]


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
