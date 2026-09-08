"""The metadata that rides along with a summary export.

Both formats carry the same record: the zip as ``metadata.json`` next to a
``README.txt`` describing the files, the PDF as text pages. The sample part is
exactly what the "data selection" page shows in its metadata accordion, so
the two are built by one function here.
"""

import datetime
from typing import Any
from zoneinfo import ZoneInfo

from spectra_inspector.utilities.model import CombinedMetadata
from spectra_inspector.utilities.scaling import get_axis

SAMPLE_INFORMATION_KEY = "Sample Information"


def sample_record(
    sample_metadata: dict[str, Any] | None, dataset: str | None
) -> dict | None:
    """The sample CSV record a dataset maps to, if the sample sheet has one."""
    if not sample_metadata or not dataset:
        return None
    sample_id = (sample_metadata.get("map_samples") or {}).get(dataset)
    if sample_id is None:
        return None
    records = sample_metadata.get("records") or []
    return next((r for r in records if r["sample_id"] == sample_id), None)


def sample_metadata_display_dict(
    md: CombinedMetadata,
    sample_metadata: dict[str, Any] | None = None,
    dataset: str | None = None,
) -> dict[str, Any]:
    """The dict the data-selection page renders as a nested accordion: the
    combined image metadata plus the sample sheet record, when there is one."""
    meta_dict = md.model_dump()
    record = sample_record(sample_metadata, dataset)
    if record:
        meta_dict[SAMPLE_INFORMATION_KEY] = record
    return meta_dict


def subselection_metadata(
    md: CombinedMetadata,
    index0_range: list[int] | tuple[int, int],
    index1_range: list[int] | tuple[int, int],
) -> dict[str, Any]:
    """Describe the box drawn on the image panels: the index ranges it covers
    on each image axis and the same bounds in the axes' physical units.

    ``index0`` runs down the image rows and ``index1`` across the columns, the
    order the exported ``*_subset`` images are sliced in. A range is half-open,
    as the slicing is."""
    axes = {}
    for axis_id, index_range in ((0, index0_range), (1, index1_range)):
        ax = get_axis(md, axis_id)
        start, stop = (int(i) for i in index_range)
        axes[f"index{axis_id}"] = {
            "name": ax.name,
            "index_range": [start, stop],
            "bounds": [ax.offset + start * ax.scale, ax.offset + stop * ax.scale],
            "units": ax.units,
        }
    return {
        "shape": [
            int(index0_range[1]) - int(index0_range[0]),
            int(index1_range[1]) - int(index1_range[0]),
        ],
        "axes": axes,
    }


def image_panel_metadata(
    energy_ranges: list[list[float] | tuple[float, float]],
    element_labels: list[str | None],
    colormaps: list[str | None],
    has_subset: bool,
) -> list[dict[str, Any]]:
    """One entry per exported image panel, keyed by the files it produced."""
    panels = []
    for igraph, (energy_range, label, cmap) in enumerate(
        zip(energy_ranges, element_labels, colormaps, strict=True)
    ):
        stem = f"bitmap_{str(igraph).zfill(2)}"
        element = label if label and label != "none" else None
        if element is not None:
            stem += f"_{element}"
        panels.append(
            {
                "file": f"{stem}.png",
                "subset_file": f"{stem}_subset.png" if has_subset else None,
                "element": element,
                "energy_range_keV": [float(e) for e in energy_range],
                "colormap": cmap,
            }
        )
    return panels


def build_export_metadata(
    dataset: str | None,
    md: CombinedMetadata | None,
    sample_metadata: dict[str, Any] | None = None,
    spectrum_only: bool = False,
    index_ranges: tuple[list[int], list[int]] | None = None,
    images: list[dict[str, Any]] | None = None,
    zeroed_elements: list[str] | None = None,
    show_peak_windows: bool | None = None,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """The full record written with an export. ``md`` may be None when the
    server could not be reached for the metadata; the record then says so
    rather than the export failing."""
    now = now or datetime.datetime.now(tz=ZoneInfo("UTC"))
    subselection = None
    if md is not None and index_ranges is not None and not spectrum_only:
        subselection = subselection_metadata(md, *index_ranges)
    return {
        "generated_utc": now.isoformat(),
        "dataset": dataset,
        "spectrum_only": spectrum_only,
        "sample": (
            sample_metadata_display_dict(md, sample_metadata, dataset)
            if md is not None
            else None
        ),
        "subselection": subselection,
        "images": list(images or []),
        "spectrum": {
            "zeroed_elements": list(zeroed_elements or []),
            "peak_windows_shown": show_peak_windows,
        },
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, list | tuple):
        return ", ".join(_fmt(v) for v in value)
    return str(value)


def flatten_for_display(d: dict[str, Any], indent: int = 0) -> list[str]:
    """Nested dict -> indented ``key: value`` lines, dict values on their own
    heading line with their contents indented below."""
    lines = []
    pad = "  " * indent
    for key, value in d.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.extend(flatten_for_display(value, indent + 1))
        else:
            lines.append(f"{pad}{key}: {_fmt(value)}")
    return lines


def subselection_lines(subselection: dict[str, Any] | None) -> list[str]:
    """Human-readable lines for the box, for the README and the PDF."""
    if subselection is None:
        return ["No box drawn: the images cover the full map."]
    lines = [f"Box shape (rows, columns): {_fmt(subselection['shape'])}"]
    for key, ax in subselection["axes"].items():
        lo, hi = ax["bounds"]
        i0, i1 = ax["index_range"]
        lines.append(
            f"{key} ({ax['name']}): indices [{i0}, {i1}), "
            f"{_fmt(lo)} to {_fmt(hi)} {ax['units']}"
        )
    return lines


_FIXED_FILE_DESCRIPTIONS = {
    "metadata.json": "this record as JSON: sample metadata, box bounds, panels",
    "README.txt": "this file",
    "spectrum.png": "the spectrum as plotted, peak windows included when shown",
    "spectrum.msa": "the spectrum in EMSA/MAS format",
    "spectrum.csv": "the spectrum as energy_keV,intensity columns",
    "ElementWeights.txt": "element weights (tab separated), zeroed-out elements as 0",
    "SpectraInspectorSummary.pdf": "the PDF summary",
}


def readme_text(metadata: dict[str, Any], files: list[str]) -> str:
    """The README written into the zip."""
    lines = [
        "Spectra Inspector summary export",
        "================================",
        "",
        f"Dataset: {metadata.get('dataset')}",
        f"Generated (UTC): {metadata.get('generated_utc')}",
        f"Spectrum only: {metadata.get('spectrum_only')}",
        "",
        "Files",
        "-----",
    ]
    described = dict(_FIXED_FILE_DESCRIPTIONS)
    for image in metadata.get("images") or []:
        window = _fmt(image["energy_range_keV"])
        element = image["element"] or "custom range"
        described[image["file"]] = (
            f"map of the {element} window, {window} keV, colormap {image['colormap']}"
        )
        if image["subset_file"]:
            described[image["subset_file"]] = f"the box region of {image['file']}"
    for f in sorted(files):
        description = described.get(f)
        lines.append(f"{f}: {description}" if description else f)

    lines.extend(["", "Box subselection", "----------------"])
    lines.extend(subselection_lines(metadata.get("subselection")))

    spectrum = metadata.get("spectrum") or {}
    zeroed = spectrum.get("zeroed_elements") or []
    lines.extend(["", "Spectrum", "--------"])
    lines.append(f"Zeroed-out elements: {', '.join(zeroed) if zeroed else 'none'}")
    lines.append(f"Peak windows shown: {spectrum.get('peak_windows_shown')}")

    sample = metadata.get("sample")
    lines.extend(["", "Sample metadata", "---------------"])
    if sample is None:
        lines.append("unavailable: the server could not be reached for it")
    else:
        lines.extend(flatten_for_display(sample))
    return "\n".join(lines) + "\n"
