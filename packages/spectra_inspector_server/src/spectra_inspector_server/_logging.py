import logging

spectraLogger = logging.getLogger("spectra_inspector")

_formatter = logging.Formatter("%(name)s : [%(levelname)s ] %(asctime)s:  %(message)s")

if not spectraLogger.handlers:
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(_formatter)
    spectraLogger.addHandler(stream_handler)
