from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from spectra_inspector_server._database.sample_metadata import SampleMetadataMapper
from spectra_inspector_server._logging import spectraLogger
from spectra_inspector_server.model import EDAX_file_set
from spectra_inspector_server.processor.utilities import _map_to_sample_name

if TYPE_CHECKING:
    from spectra_inspector_server._file_tree_handling import EDAXPathHandler


@dataclass
class InspectionProgress:
    directories_scanned: int = 0
    datasets_found: int = 0
    log_every: int = 100
    # stop the traversal once this many datasets have been found. None means
    # walk the whole tree.
    max_datasets: int | None = None

    # a method rather than a property so that mypy does not narrow it to False
    # for the rest of a scope after the first check.
    def limit_reached(self) -> bool:
        return (
            self.max_datasets is not None and self.datasets_found >= self.max_datasets
        )


class OnDiskDatabase:
    available_maps: dict[str, EDAX_file_set]
    sample_metadata_csv: str
    sample_metadata_fullpath: Path | None = None
    allow_mixed_basenames: bool
    # cap on the number of datasets a scan will register. None means no limit.
    max_datasets: int | None
    # whether the most recent scan stopped early on max_datasets, i.e. whether
    # available_maps is a truncated view of what is on disk.
    scan_truncated: bool = False
    # the subdirectory of data_root the database currently describes. None means
    # the whole of data_root (or, in desktop mode, nothing scanned yet).
    working_directory: Path | None = None

    def __init__(
        self,
        ph: "EDAXPathHandler",
        init_db: bool = True,
        sample_metadata_csv: str = "sample_metadata.csv",
        allow_mixed_basenames: bool = False,
        max_datasets: int | None = None,
    ):
        self.sample_metadata_csv = sample_metadata_csv
        self.available_maps = {}
        self.allow_mixed_basenames = allow_mixed_basenames
        self.max_datasets = max_datasets
        if init_db:
            self.inspect(ph)

    def _clear(self) -> None:
        self.available_maps = {}
        self._available_samples = None
        self.scan_truncated = False

    def refresh(self, ph: "EDAXPathHandler") -> None:
        self._clear()
        if self.working_directory is not None:
            self.set_working_directory(ph, self.working_directory)
        else:
            self.inspect(ph)

    def inspect(self, ph: "EDAXPathHandler") -> None:
        spectraLogger.info(f"Inspecting {ph.data_root}")
        progress = _recursive_inspection(
            ph.data_root,
            self,
            allow_mixed_basenames=self.allow_mixed_basenames,
            max_datasets=self.max_datasets,
        )
        self.scan_truncated = progress.limit_reached()
        self._locate_sample_metadata(ph.data_root)

    def set_working_directory(
        self,
        ph: "EDAXPathHandler",
        directory: str | Path,
        recursive: bool = True,
    ) -> Path:
        """Rescan a single directory (optionally recursively), replacing the
        contents of the database with whatever is found there.

        The caller is responsible for confirming that ``directory`` is inside
        ``ph.data_root`` -- see ``_file_browser.resolve_within_root``.
        """
        target = Path(directory)
        if not target.is_dir():
            msg = f"Not a directory: {target}"
            raise NotADirectoryError(msg)

        self._clear()
        self.working_directory = target
        spectraLogger.info(f"Inspecting working directory {target} ({recursive=})")
        progress = _recursive_inspection(
            target,
            self,
            allow_mixed_basenames=self.allow_mixed_basenames,
            recursive=recursive,
            max_datasets=self.max_datasets,
        )
        self.scan_truncated = progress.limit_reached()
        # prefer a metadata csv alongside the data, fall back to the one at the
        # data root.
        self._locate_sample_metadata(target, ph.data_root)
        return target

    def _locate_sample_metadata(self, *directories: Path) -> None:
        self.sample_metadata_fullpath = None
        for directory in directories:
            smp = directory / self.sample_metadata_csv
            if smp.is_file():
                msg = f"Found sample metadata csv at {smp}"
                spectraLogger.debug(msg)
                self.sample_metadata_fullpath = smp
                return
        msg = f"Could not find {self.sample_metadata_csv} in {directories}"
        spectraLogger.debug(msg)

    def add_fileset(
        self, basename: str, files: dict[str, Path] | EDAX_file_set
    ) -> bool:
        """Register a fileset under ``basename``.

        Returns True when the fileset was added, False when ``basename`` is
        already registered (in which case the new fileset is skipped and a
        warning is emitted).
        """
        if not isinstance(files, EDAX_file_set):
            new_set = EDAX_file_set(**files)
        else:
            new_set = files

        existing = self.available_maps.get(basename)
        if existing is not None:
            spectraLogger.warning(
                "Duplicate map name! Skipping %s, the name %s is already "
                "registered for %s.",
                new_set.spd,
                basename,
                existing.spd,
            )
            return False

        spectraLogger.debug(f"adding {basename} to available_maps")
        self.available_maps[basename] = new_set
        return True

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


def get_expected_files(spd_file: Path) -> dict[str, Path]:
    # useful for testing
    basename = spd_file.stem

    file_set_args = {}
    for ext in _possible_exts:
        newfi = basename + ext
        file_set_args[ext.replace(".", "")] = spd_file.parent / newfi

    return file_set_args


def _inventory_directory(directory: Path) -> tuple[dict[str, list[Path]], list[Path]]:
    files: dict[str, list[Path]] = {
        "spd": [],
        "spc": [],
        "ipr": [],
        "bmp": [],
        "xml": [],
    }
    subdirs: list[Path] = []

    for p in directory.iterdir():
        if p.is_file() and p.suffix.lower().lstrip(".") in files:
            files[p.suffix.lower().lstrip(".")].append(p)
        elif p.is_dir():
            subdirs.append(p)

    return files, subdirs


def _recursive_inspection(
    dirname: Path,
    db: OnDiskDatabase,
    allow_mixed_basenames: bool = False,
    progress: InspectionProgress | None = None,
    recursive: bool = True,
    max_datasets: int | None = None,
) -> InspectionProgress:
    """Walk ``dirname``, registering every EDAX file set found into ``db``.

    Returns the progress of the walk, whose ``limit_reached()`` reports whether
    ``max_datasets`` cut it short.
    """
    if progress is None:
        progress = InspectionProgress(max_datasets=max_datasets)

    if progress.limit_reached():
        return progress

    if dirname.is_dir():
        progress.directories_scanned += 1
        if progress.directories_scanned % progress.log_every == 0:
            spectraLogger.info(
                "Inspected %d directories, found %d datasets",
                progress.directories_scanned,
                progress.datasets_found,
            )

        try:
            files, subdirs = _inventory_directory(dirname)
        except OSError:
            # an unreadable directory somewhere in the tree should not abort the
            # whole scan.
            spectraLogger.warning("Could not read directory %s, skipping", dirname)
            return progress

        # check for edax files
        for edax_set in _check_files_in_directory(
            dirname,
            allow_mixed_basenames=allow_mixed_basenames,
            inventoried_files=files,
        ):
            if allow_mixed_basenames:
                basename = str(edax_set.spd)
            else:
                basename = edax_set.spd.stem

            if db.add_fileset(basename, edax_set):
                progress.datasets_found += 1

            if progress.limit_reached():
                spectraLogger.info(
                    "Reached the maximum of %d datasets, stopping the scan of %s",
                    progress.max_datasets,
                    dirname,
                )
                return progress

        # go deeper if needed
        if recursive:
            # sorted so that a max_datasets cap truncates the same way on every
            # scan rather than following iterdir's filesystem order.
            for s in sorted(subdirs):
                if progress.limit_reached():
                    return progress
                _recursive_inspection(
                    s,
                    db,
                    allow_mixed_basenames=allow_mixed_basenames,
                    progress=progress,
                    recursive=recursive,
                )

    return progress


def _validate_inventory_files(
    dirname: Path | str,
    inventory: dict[str, list[Path]] | None = None,
) -> dict[str, list[Path]]:
    if inventory is None:
        return _inventory_directory(Path(dirname))[0]
    return inventory


def _check_files_in_directory(
    dirname: Path,
    allow_mixed_basenames: bool = False,
    inventoried_files: dict[str, list[Path]] | None = None,
) -> list[EDAX_file_set]:

    inventory = _validate_inventory_files(dirname, inventoried_files)

    new_edax: list[EDAX_file_set] = []

    if allow_mixed_basenames:
        new_edax += find_edax_datasets_mixed_basename(
            dirname,
            inventoried_files=inventory,
        )

    new_edax += find_edax_datasets_common_basename(
        dirname,
        inventoried_files=inventory,
    )

    return new_edax


def find_edax_datasets_common_basename(
    directory: str | Path,
    *,
    inventoried_files: dict[str, list[Path]] | None = None,
) -> list[EDAX_file_set]:

    groups: dict[str, dict[str, Path]] = {}

    inventory = _validate_inventory_files(directory, inventoried_files)

    for ext, paths in inventory.items():
        for p in paths:
            groups.setdefault(p.stem, {})[ext] = p

    datasets: list[EDAX_file_set] = []
    if not groups:
        return datasets

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
    inventoried_files: dict[str, list[Path]] | None = None,
    map_prefix: str = "map",
    fov_prefix: str = "fov",
) -> list[EDAX_file_set]:

    inventory = _validate_inventory_files(directory, inventoried_files)
    datasets: list[EDAX_file_set] = []
    groups: dict[str, dict[str, Path]] = {}

    for ext in ("spd", "spc", "xml"):
        for p in inventory[ext]:
            if p.name.startswith(map_prefix) and p.name.endswith(f"_0.{ext}"):
                groups.setdefault(p.stem, {})[ext] = p

    if not groups:
        return datasets

    iprs = sorted(p for p in inventory["ipr"] if p.name.startswith(fov_prefix))

    if not iprs:
        return datasets

    bmps = sorted(p for p in inventory["bmp"] if p.name.startswith(fov_prefix))

    for stem in sorted(groups):
        files = groups[stem]
        if {"spd", "spc", "xml"} <= files.keys():
            datasets.append(
                EDAX_file_set(
                    spd=files["spd"],
                    spc=files["spc"],
                    xml=files["xml"],
                    ipr=iprs[0],
                    bmp=bmps[0] if bmps else None,
                )
            )

    return datasets
