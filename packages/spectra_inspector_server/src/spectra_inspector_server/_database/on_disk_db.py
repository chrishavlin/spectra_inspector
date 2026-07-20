from pathlib import Path
from typing import TYPE_CHECKING

from spectra_inspector_server._database.sample_metadata import SampleMetadataMapper
from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.model import EDAX_file_set
from spectra_inspector_server.processor.utilities import _map_to_sample_name

if TYPE_CHECKING:
    from spectra_inspector_server._file_tree_handling import EDAXPathHandler


class OnDiskDatabase:
    available_maps: dict[str, EDAX_file_set]
    sample_metadata_csv: str
    sample_metadata_fullpath: Path | None = None

    def __init__(
        self,
        ph: "EDAXPathHandler",
        init_db: bool = True,
        sample_metadata_csv: str = "sample_metadata.csv",
    ):
        self.sample_metadata_csv = sample_metadata_csv
        self.available_maps = {}
        if init_db:
            self.inspect(ph)

    def refresh(self, ph: "EDAXPathHandler") -> None:
        self.available_maps = {}
        self.inspect(ph)

    def inspect(self, ph: "EDAXPathHandler") -> None:
        spectraLogger.info(f"Inspecting {ph.data_root}")
        _recursive_inspection(ph.data_root, self)

        smp = ph.data_root / self.sample_metadata_csv
        if smp.is_file():
            msg = f"Found sample metadata csv at {smp}"
            spectraLogger.debug(msg)
            self.sample_metadata_fullpath = smp
        else:
            msg = f"Could not find expected sample metadata csv at {smp}"
            spectraLogger.debug(msg)

    def add_fileset(
        self, basename: str, files: dict[str, Path] | EDAX_file_set
    ) -> None:
        if basename in self.available_maps:
            msg = f"Duplicate map name! {basename} exists already."
            raise KeyError(msg)

        if not isinstance(files, EDAX_file_set):
            new_set = EDAX_file_set(**files)
        else:
            new_set = files
        spectraLogger.debug(f"adding {basename} to available_maps")
        self.available_maps[basename] = new_set

    @property
    def sample_metadata_mapper(self) -> SampleMetadataMapper | None:
        if self.sample_metadata_fullpath:
            return SampleMetadataMapper(self.sample_metadata_fullpath)
        return None

    _available_samples: dict[str, str] | None = None

    @property
    def available_samples(self) -> dict[str, str]:
        if self._available_samples is None:
            samples = {
                mapn: _map_to_sample_name(str(mapn)) for mapn in self.available_maps
            }
            self._available_samples = samples
        return self._available_samples


_possible_exts = [".spd", ".spc", ".ipr", ".bmp", ".xml"]
_required_exts = [".spd", ".spc", ".ipr"]


def _get_expected_files(spd_file: Path) -> dict[str, Path]:
    basename = spd_file.stem

    file_set_args = {}
    for ext in _possible_exts:
        newfi = basename + ext
        file_set_args[ext.replace(".", "")] = spd_file.parent / newfi

    return file_set_args


def _has_all_files(spd_file: Path) -> bool:
    for expected_file in _get_expected_files(spd_file).values():
        if not expected_file.is_file() and expected_file.suffix in _required_exts:
            return False
    return True


def _recursive_inspection(
    dirname: Path, db: OnDiskDatabase, allow_mixed_basenames=False
) -> None:
    msg = f"inspecting input path {dirname}"
    spectraLogger.debug(msg)
    if dirname.is_dir():
        msg = f"inspecting directory {dirname}"
        spectraLogger.debug(msg)
        for fh in dirname.iterdir():
            msg = f"inspecting {fh}"
            spectraLogger.debug(msg)
            if fh.is_dir():
                _recursive_inspection(
                    fh, db, allow_mixed_basenames=allow_mixed_basenames
                )
                for edax_set in _check_files_in_directory(fh):
                    db.add_fileset(edax_set.spd.stem, edax_set)
    else:
        msg = f"{dirname} is not a directory."
        spectraLogger.debug(msg)


def _check_files_in_directory(
    dirname: Path, allow_mixed_basenames=False
) -> list[EDAX_file_set]:

    new_edax = []
    if allow_mixed_basenames:
        edax_files = find_edax_datasets_mixed_basename(dirname)
        new_edax += edax_files

    new_edax += find_edax_datasets_common_basename(dirname)
    return new_edax


def find_edax_datasets_common_basename(directory: str | Path) -> list[EDAX_file_set]:
    """
    Returns all valid EDAX datasets contained in a directory for files with a
    common basename.

    Each dataset consists of files sharing the same basename:

        basename.spd   (required)
        basename.spc   (required)
        basename.ipr   (required)
        basename.xml   (optional)
        basename.bmp   (optional)

    Returns an empty list if no complete datasets are found.
    """
    directory = Path(directory)

    groups: dict[str, dict[str, Path]] = {}

    for ext in ("spd", "spc", "ipr", "bmp", "xml"):
        for p in directory.glob(f"*.{ext}"):
            groups.setdefault(p.stem, {})[ext] = p

    datasets: list[EDAX_file_set] = []

    for stem in sorted(groups):
        files = groups[stem]

        if {"spd", "spc", "ipr"} <= files.keys():
            datasets.append(
                EDAX_file_set(
                    spd=files["spd"],
                    spc=files["spc"],
                    ipr=files["ipr"],
                    bmp=files.get("bmp"),
                    xml=files.get("xml"),
                )
            )

    return datasets


def find_edax_datasets_mixed_basename(
    directory: str | Path,
    *,
    map_prefix: str = "map",
    fov_prefix: str = "fov",
) -> list[EDAX_file_set]:
    """
    Returns all valid EDAX datasets contained in a directory for mixed basenames.

    Each dataset consists of matching:
        <map_prefix>*_0.spd
        <map_prefix>*_0.spc
        <map_prefix>*_0.xml

    All returned datasets share the first <fov_prefix>*.ipr and
    <fov_prefix>*.bmp. If no IPR exists, or no complete map triplets exist,
    an empty list is returned.
    """
    directory = Path(directory)

    # Group map files by basename (without extension)
    groups: dict[str, dict[str, Path]] = {}

    for ext in ("spd", "spc", "xml"):
        for p in directory.glob(f"{map_prefix}*_0.{ext}"):
            groups.setdefault(p.stem, {})[ext] = p

    # First FOV files (deterministic)
    iprs = sorted(directory.glob(f"{fov_prefix}*.ipr"))
    if not iprs:
        return []

    bmps = sorted(directory.glob(f"{fov_prefix}*.bmp"))

    ipr = iprs[0]
    bmp = bmps[0] if bmps else None

    datasets: list[EDAX_file_set] = []

    for stem in sorted(groups):
        files = groups[stem]
        if {"spd", "spc", "xml"} <= files.keys():
            datasets.append(
                EDAX_file_set(
                    spd=files["spd"],
                    spc=files["spc"],
                    xml=files["xml"],
                    ipr=ipr,
                    bmp=bmp,
                )
            )

    return datasets
