import logging

spectraLogger = logging.getLogger("spectra_inspector")
spectraLogger.setLevel(logging.INFO)

_formatter = logging.Formatter("%(name)s : [%(levelname)s ] %(asctime)s:  %(message)s")

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(_formatter)
spectraLogger.addHandler(stream_handler)
