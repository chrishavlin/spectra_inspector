import datetime
import shutil
import uuid
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import fpdf
import matplotlib.pyplot as plt
import pandas as pd
import plotly
from matplotlib.figure import Figure

from spectra_inspector.logging import spectraLogger
from spectra_inspector.settings import Settings


class summaryWriter:
    folder_name: Path = Path("spector-inspector")
    pdf_name: Path = Path("SpectraInspectorSummary.pdf")
    element_weights_name: Path = Path("ElementWeights.txt")
    parent_write_dir: Path
    unique_write_dir: Path
    settings: Settings

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
    ):

        for name, fig in figures.items():
            outfile = self.full_file(f"{name}.{figformat}")
            if isinstance(fig, Figure):
                fig.savefig(outfile, format=figformat, bbox_inches="tight")
                plt.close(fig)
            else:
                plotly.io.write_image(fig, outfile, format=figformat)

        spectraLogger.info(f"wrote image files to {self.write_dir}")

    def write_element_weights(self, wts: dict) -> Path:
        fi = self.full_file(self.element_weights_name)
        with open(fi, "w", encoding="utf-8") as f:
            f.writelines(f"{element}\t{weight}\n" for element, weight in wts.items())
        return fi

    def get_zip(self, include_pdf: bool = False) -> Path:

        if include_pdf:
            self.write_pdf()

        parent = self.parent_write_dir / self.unique_write_dir
        zip_fi = parent / "spector-inspector-summary"
        zfilename = shutil.make_archive(str(zip_fi), "zip", root_dir=self.write_dir)

        return Path(zfilename)

    def write_pdf(
        self,
    ):

        files = [f for f in self.write_dir.glob("*") if f.is_file()]

        bitmaps = []
        spectrum = []
        for f in files:
            if f.stem.startswith("bitmap"):
                bitmaps.append(self.write_dir / f)
            elif f.stem.startswith("spectr"):
                spectrum.append(self.write_dir / f)
        bitmaps.sort()

        pdf = fpdf.FPDF(orientation="portrait", format="A4")
        pdf.set_font("Helvetica", size=18)

        pdf.add_page()
        lines = [
            "SpectorInspector auto-generated summary PDF ",
            f"Generated: {datetime.datetime.now(tz=ZoneInfo('UTC'))}",
        ]

        pdf.write(text="\n".join(lines))

        pdf.add_page()
        pdf.cell(text="Sample metadata:")

        for fname in bitmaps + spectrum:
            pdf.add_page()
            pdf.write(text=f"{fname.stem}\n\n")
            pdf.image(fname, w=pdf.epw)

        fout = self.full_file(self.pdf_name)
        pdf.output(fout)

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
