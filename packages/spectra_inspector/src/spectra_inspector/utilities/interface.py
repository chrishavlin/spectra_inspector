import functools
import threading

import requests
from requests.adapters import HTTPAdapter

from spectra_inspector.settings import Settings
from spectra_inspector.utilities import model

# the frontend fans several requests out at once (one image-data-summed per
# image panel), so the pool has to be wide enough to hold a connection open for
# each of them. Without this, requests falls back to a pool of 10 and, more
# importantly, every call would open a fresh TCP connection.
_CONNECTION_POOL_SIZE = 16

_session_lock = threading.Lock()
_session: requests.Session | None = None


def get_session() -> requests.Session:
    """The process-wide, connection-pooled session used for every backend call.

    Sharing one session keeps connections alive between calls, which matters
    most when the backend runs with several workers: the parallel fetches skip
    the TCP handshake and go straight to whichever worker is free.
    """
    global _session  # noqa: PLW0603
    if _session is None:
        with _session_lock:
            if _session is None:
                session = requests.Session()
                adapter = HTTPAdapter(
                    pool_connections=_CONNECTION_POOL_SIZE,
                    pool_maxsize=_CONNECTION_POOL_SIZE,
                )
                session.mount("http://", adapter)
                session.mount("https://", adapter)
                _session = session
    return _session


@functools.lru_cache(maxsize=1)
def _cached_settings() -> Settings:
    # Settings() re-reads .env from disk on every instantiation (including the
    # unprefixed-key validator), and an interface is built at every call site,
    # so cache it. Mirrors the @lru_cache on the server's get_settings.
    return Settings()


class ServerRequestError(RuntimeError):
    """raised when the backend answers a request with an error status."""


def _raise_for_status(r: requests.Response) -> None:
    if r.status_code == 200:
        return

    detail = f"request failed with status {r.status_code}"
    try:
        payload = r.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get("detail"):
        detail = str(payload["detail"])
    raise ServerRequestError(detail)


class SpectraInspectorServerInterface:
    host: str
    port: str
    protocol: str

    def __init__(
        self,
        host: str | None = None,
        port: int | str | None = None,
        protocol: str = "http",
    ) -> None:

        env_settings = _cached_settings()
        if host is None:
            valid_host = env_settings.server_host
        else:
            valid_host = host

        if port is None:
            valid_port = str(env_settings.server_port)
        else:
            valid_port = str(port)

        self.host = valid_host
        self.port = valid_port
        self.protocol = protocol

    @property
    def uri(self):
        return f"{self.protocol}://{self.host}:{self.port}"

    def _get_endpoint(self, endpoint: str) -> str:
        return f"{self.uri}/{endpoint}"

    def _get(self, uri: str, params: dict | None = None) -> requests.Response:
        """Issue a GET on the shared, pooled session.

        Every call in this class goes through here so that connection reuse and
        any future retry/timeout policy apply uniformly. It is also the single
        seam the tests patch.
        """
        return get_session().get(uri, params=params)

    @property
    def connected(self):
        uri = self._get_endpoint("info")
        try:
            r = self._get(uri)
        except requests.exceptions.ConnectionError:
            return False
        else:
            return r.status_code == 200

    def get_info(self) -> model.Info:
        uri = self._get_endpoint("info")
        try:
            r = self._get(uri)
        except requests.exceptions.ConnectionError as err:
            msg = f"could not reach the backend at {self.uri}"
            raise ServerRequestError(msg) from err
        _raise_for_status(r)
        return model.Info(**r.json())

    def get_available_datasets(
        self,
        refresh_db: bool = False,
        directory_sync: dict | None = None,
    ) -> model.AvailableDatasets:
        uri = self._get_endpoint("available-datasets")

        params: dict = {"refresh_db": refresh_db}
        params.update(directory_sync or {})
        r = self._get(uri, params=params)

        return model.AvailableDatasets(**r.json())

    def browse_directory(self, path: str = "") -> model.directoryListing:
        """List the subdirectories of one directory below the server data root.

        Only available when the server runs in desktop mode.
        """
        uri = self._get_endpoint("browse-directory")
        r = self._get(uri, params={"path": path})
        _raise_for_status(r)
        return model.directoryListing(**r.json())

    def get_datasets_in_directory(
        self, path: str = "", recursive: bool = True
    ) -> model.AvailableDatasets:
        """Scan one directory below the server data root and make it the
        server's working set.

        Only available when the server runs in desktop mode.
        """
        uri = self._get_endpoint("datasets-in-directory")
        r = self._get(uri, params={"path": path, "recursive": recursive})
        _raise_for_status(r)
        return model.AvailableDatasets(**r.json())

    def get_image_metadata(
        self,
        sample_name: str,
        directory_sync: dict | None = None,
        spectrum_only: bool = False,
    ) -> model.MetadataModel:
        payload: dict = {"sample_name": sample_name, "spectrum_only": spectrum_only}
        payload.update(directory_sync or {})
        uri = self._get_endpoint("image-metadata")
        r = self._get(uri, params=payload)
        return model.MetadataModel(**r.json())

    def get_combined_image_metadata(
        self,
        sample_name: str,
        directory_sync: dict | None = None,
        spectrum_only: bool = False,
    ) -> model.CombinedMetadata:
        """``spectrum_only`` asks about the sample's ``.spc`` spectrum rather
        than its map, here and in ``get_image_spectrum``."""
        payload: dict = {"sample_name": sample_name, "spectrum_only": spectrum_only}
        payload.update(directory_sync or {})
        uri = self._get_endpoint("image-metadata-combined")
        r = self._get(uri, params=payload)
        return model.CombinedMetadata(**r.json())

    def get_image_spectrum(
        self,
        sample_name: str,
        channel_range: tuple[int, int] | None = None,
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        include_weights: bool = True,
        directory_sync: dict | None = None,
        spectrum_only: bool = False,
    ) -> model.Spectrum1dDict:

        payload: dict
        payload = {
            "sample_name": sample_name,
            "include_weights": include_weights,
            "spectrum_only": spectrum_only,
        }
        payload.update(directory_sync or {})

        if isinstance(channel_range, tuple):
            payload["channel_0"] = channel_range[0]
            payload["channel_1"] = channel_range[1]

        if isinstance(index0_range, tuple):
            payload["index0_0"] = index0_range[0]
            payload["index0_1"] = index0_range[1]

        if isinstance(index1_range, tuple):
            payload["index1_0"] = index1_range[0]
            payload["index1_1"] = index1_range[1]

        uri = self._get_endpoint("image-spectrum")
        r = self._get(uri, params=payload)
        return model.Spectrum1dDict(**r.json())

    def get_image(
        self,
        sample_name: str,
        channel_index: int,
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        directory_sync: dict | None = None,
    ) -> model.raveledImage:

        payload: dict = {
            "sample_name": sample_name,
            "channel_index": channel_index,
        }
        payload.update(directory_sync or {})
        if isinstance(index0_range, tuple):
            payload["index0_0"] = index0_range[0]
            payload["index0_1"] = index0_range[1]

        if isinstance(index1_range, tuple):
            payload["index1_0"] = index1_range[0]
            payload["index1_1"] = index1_range[1]
        uri = self._get_endpoint("image-data")
        r = self._get(uri, params=payload)
        return model.raveledImage(**r.json())

    def image_data_summed(
        self,
        sample_name: str,
        channel_range: tuple[int, int],
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        directory_sync: dict | None = None,
    ) -> model.raveledImage:

        payload: dict = {
            "sample_name": sample_name,
            "channel_0": channel_range[0],
            "channel_1": channel_range[1],
        }
        payload.update(directory_sync or {})

        if isinstance(index0_range, tuple):
            payload["index0_0"] = index0_range[0]
            payload["index0_1"] = index0_range[1]

        if isinstance(index1_range, tuple):
            payload["index1_0"] = index1_range[0]
            payload["index1_1"] = index1_range[1]

        uri = self._get_endpoint("image-data-summed")
        r = self._get(uri, params=payload)
        return model.raveledImage(**r.json())
