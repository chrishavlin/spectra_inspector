import requests

from spectra_inspector.settings import Settings
from spectra_inspector.utilities import model


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

        env_settings = Settings()
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

    @property
    def connected(self):
        uri = self._get_endpoint("info")
        try:
            r = requests.get(uri)
        except requests.exceptions.ConnectionError:
            return False
        else:
            return r.status_code == 200

    def get_info(self) -> model.Info:
        uri = self._get_endpoint("info")
        r = requests.get(uri)
        return model.Info(**r.json())

    def get_available_datasets(
        self, refresh_db: bool = False
    ) -> model.AvailableDatasets:
        uri = self._get_endpoint("available-datasets")

        r = requests.get(uri, params={"refresh_db": refresh_db})

        return model.AvailableDatasets(**r.json())

    def get_image_metadata(self, sample_name: str) -> model.MetadataModel:
        payload = {"sample_name": sample_name}
        uri = self._get_endpoint("image-metadata")
        r = requests.get(uri, params=payload)
        return model.MetadataModel(**r.json())

    def get_combined_image_metadata(self, sample_name: str) -> model.CombinedMetadata:
        payload = {"sample_name": sample_name}
        uri = self._get_endpoint("image-metadata-combined")
        r = requests.get(uri, params=payload)
        return model.CombinedMetadata(**r.json())

    def get_image_spectrum(
        self,
        sample_name: str,
        channel_range: tuple[int, int] | None = None,
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        include_weights: bool = True,
    ) -> model.Spectrum1dDict:

        payload: dict[str, str | int]
        payload = {"sample_name": sample_name, "include_weights": include_weights}

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
        r = requests.get(uri, params=payload)
        return model.Spectrum1dDict(**r.json())

    def get_image(
        self,
        sample_name: str,
        channel_index: int,
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
    ) -> model.raveledImage:

        payload = {
            "sample_name": sample_name,
            "channel_index": channel_index,
        }
        if isinstance(index0_range, tuple):
            payload["index0_0"] = index0_range[0]
            payload["index0_1"] = index0_range[1]

        if isinstance(index1_range, tuple):
            payload["index1_0"] = index1_range[0]
            payload["index1_1"] = index1_range[1]
        uri = self._get_endpoint("image-data")
        r = requests.get(uri, params=payload)
        return model.raveledImage(**r.json())

    def image_data_summed(
        self,
        sample_name: str,
        channel_range: tuple[int, int],
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
    ) -> model.raveledImage:

        payload = {
            "sample_name": sample_name,
            "channel_0": channel_range[0],
            "channel_1": channel_range[1],
        }

        if isinstance(index0_range, tuple):
            payload["index0_0"] = index0_range[0]
            payload["index0_1"] = index0_range[1]

        if isinstance(index1_range, tuple):
            payload["index1_0"] = index1_range[0]
            payload["index1_1"] = index1_range[1]

        uri = self._get_endpoint("image-data-summed")
        r = requests.get(uri, params=payload)
        return model.raveledImage(**r.json())
