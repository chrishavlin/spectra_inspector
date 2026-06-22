import asyncio
from collections.abc import AsyncGenerator

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server.model import Spectrum1dDict, raveledImage

OpsReturnType = raveledImage | Spectrum1dDict
OptionalOpsReturnType = OpsReturnType | None
LifespanGenerator = AsyncGenerator[dict[str, EDAXPathHandler | asyncio.Queue]]  # type:ignore[type-arg]
