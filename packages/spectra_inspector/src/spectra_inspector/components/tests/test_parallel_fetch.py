"""Cover the parallel image fetch and the metadata reuse it depends on.

The initial inspector load builds one image panel per figure, and each panel's
image-data-summed call is the slow part. These pin down that the fetches really
do overlap, that they come back in the caller's order, and that the metadata is
fetched once for the batch rather than once per panel.
"""

import threading
import time

import numpy as np
import pytest

from spectra_inspector.components import bitmap_image
from spectra_inspector.components.bitmap_image import (
    fetch_im_data,
    fetch_im_data_parallel,
)
from spectra_inspector.user_store_model import UserStore
from spectra_inspector.utilities.model import CombinedMetadata, EDAX_axis

RANGES = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]


@pytest.fixture
def md():
    # only axes_by_index[2] (the channel axis) is read on this path, so build
    # that and skip validating the metadata tree these tests never touch
    channel_axis = EDAX_axis(
        size=1024,
        index_in_array=2,
        name="Energy",
        scale=0.01,
        offset=0,
        units="keV",
        navigate=False,
    )
    return CombinedMetadata.model_construct(axes_by_index={2: channel_axis})


class _RecordingInterface:
    """Stands in for the server, recording concurrency as it goes."""

    def __init__(self, delay=0.05):
        self.delay = delay
        self.lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls = []
        self.directory_syncs = []

    def __call__(self, *_args, **_kwargs):
        return self

    def image_data_summed(self, _sample_name, channel_range, directory_sync=None):
        self.directory_syncs.append(directory_sync)
        with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            self.calls.append(channel_range)
        try:
            time.sleep(self.delay)
        finally:
            with self.lock:
                self.in_flight -= 1
        # encode the range so results can be matched back to their request
        value = float(channel_range[0])
        return type(
            "raveled", (), {"image": [value, value, value, value], "shape": (2, 2)}
        )()


def test_parallel_fetch_overlaps_and_preserves_order(mocker, md):
    recorder = _RecordingInterface()
    mocker.patch.object(bitmap_image, "SpectraInspectorServerInterface", recorder)

    store = UserStore(selected_dataset="a-sample")
    results = fetch_im_data_parallel(store, RANGES, md)

    # all three were genuinely in flight together
    assert recorder.max_in_flight == len(RANGES)
    assert len(recorder.calls) == len(RANGES)

    # and results line up with the ranges the caller asked for, in order
    serial = [fetch_im_data(store, rng, md) for rng in RANGES]
    assert len(results) == len(serial)
    for parallel_result, serial_result in zip(results, serial, strict=True):
        assert parallel_result.shape == serial_result.shape
        assert np.array_equal(parallel_result, serial_result)


def test_every_parallel_fetch_carries_the_working_directory(mocker, md):
    """Each concurrent fetch can land on a different server worker, so each one
    has to carry the directory that worker may need to catch up on."""
    recorder = _RecordingInterface()
    mocker.patch.object(bitmap_image, "SpectraInspectorServerInterface", recorder)

    store = UserStore(
        selected_dataset="a-sample",
        working_directory="session-a",
        working_directory_recursive=False,
    )
    fetch_im_data_parallel(store, RANGES, md)

    expected = {
        "working_directory": "session-a",
        "working_directory_recursive": False,
    }
    assert recorder.directory_syncs == [expected] * len(RANGES)


def test_fetch_omits_the_sync_before_a_directory_is_committed(mocker, md):
    """ "" is a real directory (the data root), so only None may be dropped."""
    recorder = _RecordingInterface()
    mocker.patch.object(bitmap_image, "SpectraInspectorServerInterface", recorder)

    store = UserStore(selected_dataset="a-sample")
    assert store.working_directory is None
    fetch_im_data_parallel(store, RANGES[:1], md)
    assert recorder.directory_syncs == [{}]

    root_store = UserStore(selected_dataset="a-sample", working_directory="")
    fetch_im_data_parallel(root_store, RANGES[:1], md)
    assert recorder.directory_syncs[-1] == {
        "working_directory": "",
        "working_directory_recursive": True,
    }


def test_single_panel_skips_the_thread_pool(mocker, md):
    recorder = _RecordingInterface()
    mocker.patch.object(bitmap_image, "SpectraInspectorServerInterface", recorder)

    store = UserStore(selected_dataset="a-sample")
    results = fetch_im_data_parallel(store, RANGES[:1], md)

    assert len(results) == 1
    assert recorder.max_in_flight == 1


def test_max_parallel_of_one_falls_back_to_serial(mocker, md):
    """The opt-out, for anyone who would rather not fan out."""
    recorder = _RecordingInterface()
    mocker.patch.object(bitmap_image, "SpectraInspectorServerInterface", recorder)
    mocker.patch.object(
        bitmap_image,
        "Settings",
        return_value=mocker.Mock(max_parallel_image_fetches=1),
    )

    store = UserStore(selected_dataset="a-sample")
    results = fetch_im_data_parallel(store, RANGES, md)

    assert len(results) == len(RANGES)
    assert recorder.max_in_flight == 1  # never more than one request at a time
    # scale 0.01 / offset 0, so the keV ranges map onto these channel indices
    assert recorder.calls == [(0, 100), (100, 200), (200, 300)]


def test_get_new_im_reuses_supplied_metadata(mocker, md):
    """Passing md must stop get_new_im refetching it per panel."""
    store = UserStore(selected_dataset="a-sample")
    fetch_md = mocker.patch.object(
        UserStore, "conditionally_fetch_metadata", return_value=md
    )

    im_data = np.arange(4, dtype=float).reshape(2, 2)
    bitmap_image.get_new_im(store, RANGES[0], "viridis", im_data=im_data, md=md)
    assert fetch_md.call_count == 0

    # without md it falls back to fetching, as before
    bitmap_image.get_new_im(store, RANGES[0], "viridis", im_data=im_data)
    assert fetch_md.call_count == 1
