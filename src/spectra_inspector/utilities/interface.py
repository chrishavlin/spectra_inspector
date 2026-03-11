_DEFAULT_DEBUG_HOST = '0.0.0.0'
_DEFAULT_DEBUG_PORT = 8000

import requests

from spectra_inspector.utilities import model

class SpectraInspectorServerInterface:
    host: str
    port: str
    protocol: str

    def __init__(self,
                 host: str | None = None,
                 port: int | str | None = None,
                 protocol: str = 'http') -> None:
        if host is None:
            valid_host = _DEFAULT_DEBUG_HOST
        else:
            valid_host = host

        if port is None:
            valid_port = str(_DEFAULT_DEBUG_PORT)
        else:
            valid_port = str(port)

        self.host = valid_host
        self.port = valid_port
        self.protocol = protocol

    @property
    def uri(self):
        return f"{self.protocol}://{self.host}:{self.port}"

    def _get_endpoint(self, endpoint:str) -> str:
        return f"{self.uri}/{endpoint}"

    @property
    def connected(self):
        uri = self._get_endpoint('info')
        r = requests.get(uri)
        return r.status_code == 200

    def get_info(self) -> model.Info:
        uri = self._get_endpoint('info')
        r = requests.get(uri)
        return model.Info(**r.json())

    def get_available_datasets(self) -> model.AvailableDatasets:
        uri = self._get_endpoint('available-datasets')
        r = requests.get(uri)
        return model.AvailableDatasets(**r.json())

    def get_image_metadata(self, sample_name: str) -> model.MetadataModel:
        payload = {"sample_name": sample_name}
        uri = self._get_endpoint('image-metadata')
        r = requests.get(uri, params=payload)
        return model.MetadataModel(**r.json())
    
    def get_image_spectrum(self, sample_name: str) -> model.Spectrum1dDict: 
        payload = {"sample_name": sample_name}
        uri = self._get_endpoint('image-spectrum')
        r = requests.get(uri, params=payload)        
        return model.Spectrum1dDict(**r.json())


