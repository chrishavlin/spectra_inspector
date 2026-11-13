import datetime
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import fpdf
import matplotlib.pyplot as plt
import pandas as pd
import plotly
import pptx
from matplotlib.figure import Figure
from PIL import Image
from pptx.slide import Slide
from pptx.util import Inches, Pt

from spectra_inspector.logging import spectraLogger
from spectra_inspector.settings import Settings
from spectra_inspector.utilities.export_metadata import (
    flatten_for_display,
    readme_text,
    subselection_lines,
)
from spectra_inspector.utilities.image_export import (
    FIGURE_DPI,
    image_axes,
    page_scale_factor,
    render_image_figure,
)

# the core PDF fonts are latin-1 only; anything else (a µm axis unit is fine, a
# CJK sample description is not) is replaced rather than failing the export
_PDF_ENCODING = "latin-1"


def _pdf_safe(text: str) -> str:
    return text.encode(_PDF_ENCODING, errors="replace").decode(_PDF_ENCODING)


# the deck is 16:9. PowerPoint does not paginate text the way fpdf does, so the
# metadata is split over slides by line count: this many lines of the body font
# fit under a slide title.
_PPTX_WIDTH = Inches(13.333)
_PPTX_HEIGHT = Inches(7.5)
_PPTX_MARGIN = Inches(0.5)
_PPTX_TITLE_HEIGHT = Inches(0.8)
_PPTX_BODY_FONT = "Courier New"
_PPTX_BODY_PT = 10
_PPTX_LINES_PER_SLIDE = 34


class summaryWriter:
    folder_name: Path = Path("spector-inspector")
    pdf_name: Path = Path("SpectraInspectorSummary.pdf")
    pptx_name: Path = Path("SpectraInspectorSummary.pptx")
    element_weights_name: Path = Path("ElementWeights.txt")
    metadata_name: Path = Path("metadata.json")
    readme_name: Path = Path("README.txt")
    parent_write_dir: Path
    unique_write_dir: Path
    settings: Settings
    # the record `build_export_metadata` produces, once `set_export_metadata`
    # has been called; the PDF, the deck and the zip's json/README are rendered
    # from it
    export_metadata: dict[str, Any] | None = None

    def __init__(
        self,
        folder_name: Path | str = "spector_inspector",
        cleanup_tmp_dirs: bool = True,
        settings: Settings | None = None,
    ):
        if settings is None:
            settings = Settings()

        self.settings = settings
        self.unique_write_dir = Path(uuid.uuid4().hex)
        self.parent_write_dir = Path(self.settings.write_dir)
        self.folder_name = Path(folder_name)

        if self.parent_write_dir.is_dir() is False:
            self.parent_write_dir.mkdir()

        if cleanup_tmp_dirs:
            self.clean_parent()

        # the unique subdir under which we write this write session's files
        uniq = self.parent_write_dir / self.unique_write_dir
        uniq.mkdir()

        # the full write directory
        w = self.write_dir
        w.mkdir()

    def clean_parent(self):
        max_dirs = self.settings.max_tmp_dirs

        dirs = [f for f in self.parent_write_dir.glob("*") if f.is_dir()]
        n_dirs_to_rm = len(dirs) - max_dirs
        if n_dirs_to_rm > 0:
            mod_times = [f.stat().st_mtime_ns for f in dirs]
            mod_times.sort(reverse=True)
            delete_these = [
                f for _, f in sorted(zip(mod_times, dirs, strict=True), reverse=True)
            ][:n_dirs_to_rm]
            for f in delete_these:
                shutil.rmtree(f)
            spectraLogger.info(f"deleted {len(delete_these)} temp directories")

    @property
    def write_dir(self) -> Path:
        return self.parent_write_dir / self.unique_write_dir / self.folder_name

    def full_file(self, f: str | Path) -> Path:
        return self.write_dir / Path(f)

    def write_static_figures(
        self,
        figures: dict[str, Figure | plotly.graph_objs.Figure],
        figformat: Literal["png", "svg", "pdf"] = "png",
        scale_factor: int | None = None,
    ):
        """Save the figures. An image panel's figure is written through
        ``image_export`` with its map reduced by ``scale_factor`` (1 keeps
        every pixel), or by whatever fits it on a page when none is given; any
        other figure is saved as it is."""
        for name, fig in figures.items():
            outfile = self.full_file(f"{name}.{figformat}")
            if isinstance(fig, Figure):
                ax = image_axes(fig) if figformat == "png" else None
                if ax is not None:
                    factor = scale_factor or page_scale_factor(
                        ax.images[0].get_array().shape[:2]
                    )
                    render_image_figure(fig, factor).save(outfile)
                else:
                    fig.savefig(
                        outfile, format=figformat, bbox_inches="tight", dpi=FIGURE_DPI
                    )
                plt.close(fig)
            else:
                plotly.io.write_image(fig, outfile, format=figformat)

        spectraLogger.info(f"wrote image files to {self.write_dir}")

    def write_element_weights(self, wts: dict) -> Path:
        fi = self.full_file(self.element_weights_name)
        with open(fi, "w", encoding="utf-8") as f:
            f.writelines(f"{element}\t{weight}\n" for element, weight in wts.items())
        return fi

    def set_export_metadata(self, metadata: dict[str, Any]) -> None:
        self.export_metadata = metadata

    def write_metadata_files(self) -> tuple[Path, Path]:
        """Write the export record as ``metadata.json`` and a ``README.txt``
        listing every file that will end up in the zip (these two included)."""
        if self.export_metadata is None:
            msg = "set_export_metadata must be called before writing the metadata"
            raise RuntimeError(msg)

        json_file = self.full_file(self.metadata_name)
        json_file.write_text(
            json.dumps(self.export_metadata, indent=2, default=str), encoding="utf-8"
        )

        readme = self.full_file(self.readme_name)
        files = [f.name for f in self.write_dir.glob("*") if f.is_file()]
        if readme.name not in files:
            files.append(readme.name)
        readme.write_text(readme_text(self.export_metadata, files), encoding="utf-8")
        return json_file, readme

    def get_zip(self, include_pdf: bool = False) -> Path:

        if include_pdf:
            self.write_pdf()

        parent = self.parent_write_dir / self.unique_write_dir
        zip_fi = parent / "spector-inspector-summary"
        zfilename = shutil.make_archive(str(zip_fi), "zip", root_dir=self.write_dir)

        return Path(zfilename)

    def _metadata_sections(self) -> list[tuple[str, list[str]]]:
        """The sample metadata (as the data-selection accordion shows it) and
        the subselection, as headed blocks of text lines; a single block saying
        so when no record was set. The PDF and the deck both render these."""
        md = self.export_metadata
        if md is None:
            return [("Sample metadata", ["not available for this export"])]

        header = [
            f"dataset: {md.get('dataset')}",
            f"generated: {md.get('generated_utc')}",
        ]
        sample = md.get("sample")
        body = (
            flatten_for_display(sample)
            if sample is not None
            else ["unavailable: the server could not be reached for it"]
        )
        return [
            ("Sample metadata", [*header, "", *body]),
            ("Subselection", subselection_lines(md.get("subselection"))),
        ]

    def _summary_images(self) -> list[Path]:
        """The rendered images in presentation order: the image panels (each
        followed by its subset), then the spectrum."""
        bitmaps = []
        spectrum = []
        for f in self.write_dir.glob("*.png"):
            if f.stem.startswith("bitmap"):
                bitmaps.append(f)
            elif f.stem.startswith("spectr"):
                spectrum.append(f)
        return sorted(bitmaps) + sorted(spectrum)

    def _pdf_metadata_pages(self, pdf: fpdf.FPDF) -> None:
        pdf.add_page()
        for i, (heading, lines) in enumerate(self._metadata_sections()):
            if i > 0:
                pdf.ln(4)
            pdf.set_font("Helvetica", size=14)
            pdf.cell(text=heading, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Courier", size=8)
            pdf.multi_cell(w=0, text=_pdf_safe("\n".join(lines)))

    def write_pdf(
        self,
    ):
        pdf = fpdf.FPDF(orientation="portrait", format="A4")
        pdf.set_font("Helvetica", size=18)

        pdf.add_page()
        lines = [
            "SpectorInspector auto-generated summary PDF ",
            f"Generated: {datetime.datetime.now(tz=ZoneInfo('UTC'))}",
        ]

        pdf.write(text="\n".join(lines))

        self._pdf_metadata_pages(pdf)
        pdf.set_font("Helvetica", size=18)

        for fname in self._summary_images():
            pdf.add_page()
            pdf.write(text=f"{fname.stem}\n\n")
            # as wide as the page, unless a tall image would then run off it
            with Image.open(fname) as im:
                aspect = im.width / im.height
            room = pdf.h - pdf.b_margin - pdf.get_y()
            pdf.image(fname, w=min(pdf.epw, room * aspect))

        fout = self.full_file(self.pdf_name)
        pdf.output(fout)

    @staticmethod
    def _pptx_text(
        slide: Slide,
        lines: list[str],
        top: int,
        height: int,
        size_pt: int,
        font: str | None = None,
    ) -> None:
        box = slide.shapes.add_textbox(
            _PPTX_MARGIN, top, _PPTX_WIDTH - 2 * _PPTX_MARGIN, height
        )
        frame = box.text_frame
        frame.word_wrap = True
        frame.text = "\n".join(lines)
        for paragraph in frame.paragraphs:
            paragraph.font.size = Pt(size_pt)
            if font is not None:
                paragraph.font.name = font

    def write_pptx(self) -> None:
        """Write the summary as a 16:9 deck with the PDF's content: a title
        slide, the metadata as text, then one slide per rendered image.

        The images are placed as pictures scaled to fit under the slide title,
        so their pixel size only sets how sharp they are, not how large they
        appear.
        """
        deck = pptx.Presentation()
        deck.slide_width = _PPTX_WIDTH
        deck.slide_height = _PPTX_HEIGHT
        # the blank layout: every box is placed explicitly, so the deck does not
        # depend on the default template's placeholders
        layout = deck.slide_layouts[6]
        body_top = _PPTX_MARGIN + _PPTX_TITLE_HEIGHT
        body_height = _PPTX_HEIGHT - body_top - _PPTX_MARGIN

        def new_slide(title: str) -> Slide:
            slide = deck.slides.add_slide(layout)
            self._pptx_text(slide, [title], _PPTX_MARGIN, _PPTX_TITLE_HEIGHT, 24)
            return slide

        slide = new_slide("Spectra Inspector auto-generated summary")
        self._pptx_text(
            slide,
            [f"Generated: {datetime.datetime.now(tz=ZoneInfo('UTC'))}"],
            body_top,
            body_height,
            14,
        )

        for heading, lines in self._metadata_sections():
            for start in range(0, len(lines), _PPTX_LINES_PER_SLIDE):
                title = heading if start == 0 else f"{heading} (continued)"
                self._pptx_text(
                    new_slide(title),
                    lines[start : start + _PPTX_LINES_PER_SLIDE],
                    body_top,
                    body_height,
                    _PPTX_BODY_PT,
                    font=_PPTX_BODY_FONT,
                )

        body_width = _PPTX_WIDTH - 2 * _PPTX_MARGIN
        for fname in self._summary_images():
            slide = new_slide(fname.stem)
            with Image.open(fname) as im:
                px_width, px_height = im.size
            scale = min(body_width / px_width, body_height / px_height)
            width, height = int(px_width * scale), int(px_height * scale)
            slide.shapes.add_picture(
                str(fname),
                int((_PPTX_WIDTH - width) / 2),
                int(body_top + (body_height - height) / 2),
                width=width,
                height=height,
            )

        deck.save(str(self.full_file(self.pptx_name)))

    def get_pptx_path(self) -> Path:
        fout = self.full_file(self.pptx_name)
        if not fout.is_file():
            self.write_pptx()
        return fout

    def get_pdf_path(self, generate_pdf: bool = True):
        fout = self.full_file(self.pdf_name)
        if fout.is_file() is False and generate_pdf:
            self.write_pdf()

        return fout

    def write_MSA(
        self,
        active_spectrum_metadata: dict,
        file_format: Literal["Y", "XY"] | None = None,
        file_type: Literal[".msa", ".csv"] | None = None,
    ) -> Path:

        intensity = active_spectrum_metadata["intensity"]
        energy = active_spectrum_metadata["energy"]
        attrs = active_spectrum_metadata["attrs"]

        file_type = file_type or ".msa"

        if file_type == ".msa":
            from rsciio.msa import file_writer

            f = self.full_file("spectrum.msa")
            signal = {
                "data": intensity,
                "axes": [
                    {
                        "size": len(intensity),
                        "index_in_array": 0,
                        "name": "Energy",
                        "scale": energy[1] - energy[0],
                        "offset": energy[0],
                        "units": "keV",
                        "navigate": False,
                    }
                ],
                "metadata": attrs["metadata"],
                "original_metadata": attrs["original_metadata"],
            }

            file_format = file_format or "XY"
            file_writer(f, signal, format=file_format)

        elif file_type == ".csv":
            f = self.full_file("spectrum.csv")
            df = pd.DataFrame({"energy_keV": energy, "intensity": intensity})
            df.to_csv(f, index=False)

        return f
