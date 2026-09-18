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
    polygon: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Describe the selection drawn on the image panels: the index ranges it
    covers on each image axis and the same bounds in the axes' physical
    units, plus the corners of a polygon when that is what was drawn (the
    ranges are then its bounding box).

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
    record: dict[str, Any] = {
        "kind": "box" if polygon is None else "polygon",
        "shape": [
            int(index0_range[1]) - int(index0_range[0]),
            int(index1_range[1]) - int(index1_range[0]),
        ],
        "axes": axes,
    }
    if polygon is not None:
        # corners in pixel index units, [index0, index1], and in the axes'
        # physical units in the same order
        record["polygon"] = {
            "vertices_index": [[float(v) for v in vertex] for vertex in polygon],
            "vertices_physical": [
                [
                    get_axis(md, 0).offset + vertex[0] * get_axis(md, 0).scale,
                    get_axis(md, 1).offset + vertex[1] * get_axis(md, 1).scale,
                ]
                for vertex in polygon
            ],
        }
    return record


def _image_files(stem: str, has_subset: bool) -> dict[str, Any]:
    return {
        "file": f"{stem}.png",
        "subset_file": f"{stem}_subset.png" if has_subset else None,
    }


def single_image_metadata(
    stem: str,
    energy_range: list[float] | tuple[float, float],
    element_label: str | None,
    colormap: str | None,
    has_subset: bool,
) -> dict[str, Any]:
    """The record of one element-map panel, keyed by the files it produced."""
    element = element_label if element_label and element_label != "none" else None
    return {
        **_image_files(stem, has_subset),
        "element": element,
        "energy_range_keV": [float(e) for e in energy_range],
        "colormap": colormap,
    }


def composite_image_metadata(
    stem: str, channels: list[dict[str, Any]], has_subset: bool
) -> dict[str, Any]:
    """The record of one composite panel: no element or colormap of its own,
    but one entry per channel (see ``composite.compositeChannel.metadata``),
    channels that are off included so the numbering matches the page."""
    return {
        **_image_files(stem, has_subset),
        "element": None,
        "colormap": None,
        "channels": list(channels),
    }


def image_panel_metadata(
    energy_ranges: list[list[float] | tuple[float, float]],
    element_labels: list[str | None],
    colormaps: list[str | None],
    has_subset: bool,
) -> list[dict[str, Any]]:
    """One entry per exported element-map panel, in page order."""
    panels = []
    for igraph, (energy_range, label, cmap) in enumerate(
        zip(energy_ranges, element_labels, colormaps, strict=True)
    ):
        stem = f"bitmap_{str(igraph).zfill(2)}"
        if label and label != "none":
            stem += f"_{label}"
        panels.append(
            single_image_metadata(stem, energy_range, label, cmap, has_subset)
        )
    return panels


def image_description(image: dict[str, Any]) -> str:
    """One line saying what an exported image file holds."""
    channels = image.get("channels")
    if channels is not None:
        parts = []
        for channel in channels:
            if not channel.get("active", True):
                continue
            element = channel.get("element") or "custom range"
            window = _fmt(channel["energy_range_keV"])
            parts.append(f"{element} ({window} keV) in {channel['color']}")
        return "composite of " + "; ".join(parts) if parts else "composite, no channels"
    window = _fmt(image["energy_range_keV"])
    element = image["element"] or "custom range"
    return f"map of the {element} window, {window} keV, colormap {image['colormap']}"


def build_export_metadata(
    dataset: str | None,
    md: CombinedMetadata | None,
    sample_metadata: dict[str, Any] | None = None,
    spectrum_only: bool = False,
    index_ranges: tuple[list[int], list[int]]
    | tuple[tuple[int, int], ...]
    | None = None,
    images: list[dict[str, Any]] | None = None,
    zeroed_elements: list[str] | None = None,
    show_peak_windows: bool | None = None,
    now: datetime.datetime | None = None,
    polygon: list[list[float]] | None = None,
) -> dict[str, Any]:
    """The full record written with an export. ``md`` may be None when the
    server could not be reached for the metadata; the record then says so
    rather than the export failing. ``polygon`` carries the corners when the
    selection is one, with ``index_ranges`` its bounding box."""
    now = now or datetime.datetime.now(tz=ZoneInfo("UTC"))
    subselection = None
    if md is not None and index_ranges is not None and not spectrum_only:
        subselection = subselection_metadata(md, *index_ranges, polygon=polygon)
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
    """Human-readable lines for the selection, for the README and the PDF."""
    if subselection is None:
        return ["No box or shape drawn: the images cover the full map."]
    polygon = subselection.get("polygon")
    box = "Bounding box" if polygon else "Box"
    lines = [f"{box} shape (rows, columns): {_fmt(subselection['shape'])}"]
    for key, ax in subselection["axes"].items():
        lo, hi = ax["bounds"]
        i0, i1 = ax["index_range"]
        lines.append(
            f"{key} ({ax['name']}): indices [{i0}, {i1}), "
            f"{_fmt(lo)} to {_fmt(hi)} {ax['units']}"
        )
    if polygon:
        corners = polygon["vertices_index"]
        lines.append(
            f"Polygon with {len(corners)} corners, as (index0, index1): "
            + "; ".join(f"({_fmt(v[0])}, {_fmt(v[1])})" for v in corners)
        )
    return lines


_FIXED_FILE_DESCRIPTIONS = {
    "metadata.json": "this record as JSON: sample metadata, selection bounds, panels",
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
        described[image["file"]] = image_description(image)
        if image["subset_file"]:
            described[image["subset_file"]] = f"the selected region of {image['file']}"
    for f in sorted(files):
        description = described.get(f)
        lines.append(f"{f}: {description}" if description else f)

    lines.extend(["", "Subselection", "------------"])
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
