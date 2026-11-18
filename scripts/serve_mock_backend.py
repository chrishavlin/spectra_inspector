"""Serve the backend with its synthetic samples listed, for browser testing
without EDAX data.

The mock samples of ``spectra_inspector_server._testing`` are valid on every
endpoint while ``PYTEST_VERSION`` is set, but ``/available-datasets`` does not
list them, and the frontend's dataset dropdown clears a value that is not among
its options. This wrapper lists them, and builds the mock map at a realistic
size so callback timings resemble real maps (the stock mock is 16x16).

Run it from the server package, then start the frontend as usual and open
``/inspector/faked-dataset-C12``::

    cd packages/spectra_inspector_server
    uv run python ../../scripts/serve_mock_backend.py [--size 512] [--port 8000]

Everything outside the ``__main__`` guard runs again in the spawned worker
process, which is what carries the patches into it.
"""

from __future__ import annotations

import argparse
import os
import tempfile

os.environ.setdefault("PYTEST_VERSION", "1")
os.environ.setdefault(
    "SPECTRA_INSPECTOR_DATA_ROOT", tempfile.mkdtemp(prefix="spectra-inspector-mock-")
)

from spectra_inspector_server import _testing, main  # noqa: E402
from spectra_inspector_server._file_tree_handling import (  # noqa: E402
    EDAXPathHandler,
)
from spectra_inspector_server.model import (  # noqa: E402
    AvailableDatasets,
    EDAX_raw_ds,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--size", type=int, default=512, help="mock map edge, pixels")
    parser.add_argument("--channels", type=int, default=10)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_known_args()[0]


_ARGS = _parse_args()
_create_mock = _testing.createEDAXMock
_available_datasets = main._available_datasets_response


def _sized_mock(im_shape: tuple[int, int, int] | None = None) -> EDAX_raw_ds:
    return _create_mock(im_shape or (_ARGS.size, _ARGS.size, _ARGS.channels))


def _with_mock_samples(ph: EDAXPathHandler) -> AvailableDatasets:
    response = _available_datasets(ph)
    mock = _testing.onDiscMock()
    response.available_files = [*response.available_files, *mock.filenames]
    response.available_spectra = [
        *response.available_spectra,
        *mock.spectrum_filenames,
    ]
    return response


_testing.createEDAXMock = _sized_mock
main._available_datasets_response = _with_mock_samples

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(main.app, host=_ARGS.host, port=_ARGS.port)
