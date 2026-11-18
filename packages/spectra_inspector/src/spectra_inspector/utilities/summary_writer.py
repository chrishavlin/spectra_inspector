import datetime
import shutil
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import fpdf
import matplotlib.pyplot as plt
import pandas as pd
import pptx
from matplotlib.figure import Figure
from PIL import Image
from pptx.slide import Slide
from pptx.util import Inches, Pt

from spectra_inspector.logging import spectraLogger
from spectra_inspector.settings import Settings
from spectra_inspector.utilities.element_weights import (
    WEIGHTS_UNAVAILABLE_MSG,
    apply_zeroed_elements,
    element_weights_text,
    format_weight,
    zeroed_note,
)
from spectra_inspector.utilities.export_metadata import (
    metadata_json,
    readme_text,
    summary_lines,
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


_SUMMARY_HEADING = "Export summary"
_WEIGHTS_HEADING = "Element weights"
_ATTACHMENT_NOTE = (
    "Attached to this PDF: {files}. Open the attachments panel of your PDF "
    "viewer to get at them (some viewers, browsers' built-in ones among them, "
    "do not show attachments)."
)
_PDF_WEIGHTS_TABLE_WIDTH = 90
_NOTES_NOTE = "The full metadata record is in the speaker notes of this slide."

# the deck is 16:9
_PPTX_WIDTH = Inches(13.333)
_PPTX_HEIGHT = Inches(7.5)
_PPTX_MARGIN = Inches(0.5)
_PPTX_TITLE_HEIGHT = Inches(0.8)
_PPTX_BODY_PT = 14
_PPTX_NOTES_PT = 10
_PPTX_WEIGHTS_COLUMN_WIDTH = Inches(2.75)
_PPTX_WEIGHTS_ROW_HEIGHT = Inches(0.4)
_PPTX_WEIGHTS_NOTE_HEIGHT = Inches(0.5)


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
    # has been called; the zip's json/README, the PDF's attachment and the
    # deck's speaker notes are rendered from it
    export_metadata: dict[str, Any] | None = None
    # the weights as exported (zeroed-out elements as 0) and the elements that
    # were zeroed, once `set_element_weights` has been called; None when the
    # spectrum has no weights
    element_weights: dict[str, Any] | None = None
    zeroed_elements: tuple[str, ...] = ()

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
        figures: dict[str, Figure],
        figformat: Literal["png", "svg", "pdf"] = "png",
        scale_factor: int | None = None,
    ):
        """Save the matplotlib figures. An image panel's figure is written through
        ``image_export`` with its map reduced by ``scale_factor`` (1 keeps
        every pixel), or by whatever fits it on a page when none is given; any
        other figure is saved as it is."""
        for name, fig in figures.items():
            outfile = self.full_file(f"{name}.{figformat}")
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

        spectraLogger.info(f"wrote image files to {self.write_dir}")

    def set_element_weights(
        self, wts: dict[str, Any] | None, zeroed_elements: Iterable[str] = ()
    ) -> None:
        """Take the computed weights of the exported spectrum (None when it has
        none) and the elements the user zeroed out. Every output reports the
        zeroed elements as 0."""
        self.zeroed_elements = tuple(zeroed_elements)
        self.element_weights = (
            None if wts is None else apply_zeroed_elements(wts, self.zeroed_elements)
        )

    def write_element_weights(self) -> Path:
        if self.element_weights is None:
            msg = "there are no element weights to write"
            raise RuntimeError(msg)
        fi = self.full_file(self.element_weights_name)
        fi.write_text(element_weights_text(self.element_weights), encoding="utf-8")
        return fi

    def _weights_rows(self) -> list[tuple[str, str]]:
        return [
            (key, format_weight(key, value))
            for key, value in (self.element_weights or {}).items()
        ]

    def _weights_note(self) -> str | None:
        return zeroed_note(self.element_weights or {}, self.zeroed_elements)

    def set_export_metadata(self, metadata: dict[str, Any]) -> None:
        self.export_metadata = metadata

    def write_metadata_files(self) -> tuple[Path, Path]:
        """Write the export record as ``metadata.json`` and a ``README.txt``
        listing every file that will end up in the zip (these two included)."""
        if self.export_metadata is None:
            msg = "set_export_metadata must be called before writing the metadata"
            raise RuntimeError(msg)

        json_file = self.full_file(self.metadata_name)
        json_file.write_text(metadata_json(self.export_metadata), encoding="utf-8")

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

    def _pdf_summary_page(self, pdf: fpdf.FPDF) -> None:
        """A page with the short summary; the full record goes in as an
        embedded file rather than as pages of text."""
        lines = summary_lines(self.export_metadata)
        attached = []
        if self.export_metadata is not None:
            pdf.embed_file(
                bytes=metadata_json(self.export_metadata).encode("utf-8"),
                basename=self.metadata_name.name,
                mime_type="application/json",
                desc="Spectra Inspector export metadata",
            )
            attached.append(f"the full metadata record as {self.metadata_name.name}")
        if self.element_weights is not None:
            pdf.embed_file(
                bytes=element_weights_text(self.element_weights).encode("utf-8"),
                basename=self.element_weights_name.name,
                mime_type="text/plain",
                desc="Element weights, tab separated",
            )
            attached.append(f"the element weights as {self.element_weights_name.name}")
        if attached:
            lines += ["", _ATTACHMENT_NOTE.format(files=" and ".join(attached))]

        pdf.add_page()
        pdf.set_font("Helvetica", size=14)
        pdf.cell(text=_SUMMARY_HEADING, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(w=0, text=_pdf_safe("\n".join(lines)))

    def _pdf_weights_page(self, pdf: fpdf.FPDF) -> None:
        """A page of its own for the weights table, so that it never has to
        share the room on a page with an image."""
        pdf.add_page()
        pdf.set_font("Helvetica", size=14)
        pdf.cell(text=_WEIGHTS_HEADING, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", size=10)
        if self.element_weights is None:
            pdf.multi_cell(w=0, text=WEIGHTS_UNAVAILABLE_MSG)
            return

        with pdf.table(
            width=_PDF_WEIGHTS_TABLE_WIDTH,
            align="LEFT",
            first_row_as_headings=False,
            text_align=("LEFT", "RIGHT"),
        ) as table:
            for name, value in self._weights_rows():
                table.row((_pdf_safe(name), value))

        note = self._weights_note()
        if note is not None:
            pdf.ln(2)
            pdf.multi_cell(w=0, text=_pdf_safe(note))

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

        self._pdf_summary_page(pdf)
        pdf.set_font("Helvetica", size=18)

        for fname in self._summary_images():
            pdf.add_page()
            pdf.write(text=f"{fname.stem}\n\n")
            # as wide as the page, unless a tall image would then run off it
            with Image.open(fname) as im:
                aspect = im.width / im.height
            room = pdf.h - pdf.b_margin - pdf.get_y()
            pdf.image(fname, w=min(pdf.epw, room * aspect))

        self._pdf_weights_page(pdf)

        fout = self.full_file(self.pdf_name)
        pdf.output(fout)

    @staticmethod
    def _pptx_text(
        slide: Slide,
        lines: list[str],
        top: int,
        height: int,
        size_pt: int,
    ) -> None:
        box = slide.shapes.add_textbox(
            _PPTX_MARGIN, top, _PPTX_WIDTH - 2 * _PPTX_MARGIN, height
        )
        frame = box.text_frame
        frame.word_wrap = True
        frame.text = "\n".join(lines)
        for paragraph in frame.paragraphs:
            paragraph.font.size = Pt(size_pt)

    def write_pptx(self) -> None:
        """Write the summary as a 16:9 deck with the PDF's content: a title
        slide, the short summary, one slide per rendered image, then the
        element weights as a native table. The full metadata record is the
        summary slide's speaker notes.

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

        slide = new_slide(_SUMMARY_HEADING)
        lines = summary_lines(self.export_metadata)
        if self.export_metadata is not None:
            lines += ["", _NOTES_NOTE]
            notes = slide.notes_slide.notes_text_frame
            notes.text = metadata_json(self.export_metadata)
            for paragraph in notes.paragraphs:
                paragraph.font.size = Pt(_PPTX_NOTES_PT)
        self._pptx_text(slide, lines, body_top, body_height, _PPTX_BODY_PT)

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

        self._pptx_weights(new_slide(_WEIGHTS_HEADING), body_top, body_height)

        deck.save(str(self.full_file(self.pptx_name)))

    def _pptx_weights(self, slide: Slide, top: int, height: int) -> None:
        if self.element_weights is None:
            self._pptx_text(
                slide, [WEIGHTS_UNAVAILABLE_MSG], top, height, _PPTX_BODY_PT
            )
            return

        rows = self._weights_rows()
        row_height = min(
            _PPTX_WEIGHTS_ROW_HEIGHT,
            int((height - _PPTX_WEIGHTS_NOTE_HEIGHT) / max(len(rows), 1)),
        )
        table = slide.shapes.add_table(
            len(rows),
            2,
            _PPTX_MARGIN,
            top,
            2 * _PPTX_WEIGHTS_COLUMN_WIDTH,
            row_height * len(rows),
        ).table
        # every row is data: the default style would set the first one off as a
        # header
        table.first_row = False
        for row, values in zip(table.rows, rows, strict=True):
            row.height = row_height
            for cell, text in zip(row.cells, values, strict=True):
                cell.text = text
                for paragraph in cell.text_frame.paragraphs:
                    paragraph.font.size = Pt(_PPTX_BODY_PT)

        note = self._weights_note()
        if note is not None:
            self._pptx_text(
                slide,
                [note],
                top + row_height * len(rows),
                _PPTX_WEIGHTS_NOTE_HEIGHT,
                _PPTX_BODY_PT,
            )

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
