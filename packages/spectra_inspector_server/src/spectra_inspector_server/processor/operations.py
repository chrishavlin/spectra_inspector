from typing import Any

import numpy as np
import numpy.typing as npt

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server.model import (
    CombinedMetadata,
    EDAX_axis,
    MetadataModel,
    Spectrum1d,
    raveledImage,
)
from spectra_inspector_server.processor.utilities import _make_serializeable_dict


class OperationEDAXStateHandler:
    def __init__(self, ph: EDAXPathHandler, allow_mock_files: bool = False) -> None:
        self.ph = ph
        self._allow_mock_files = allow_mock_files

    def _require_sample(self, sample_name: str) -> None:

        if sample_name in self.ph.database.available_maps:
            return

        if self._allow_mock_files:
            from spectra_inspector_server._testing import _on_disc_mock  # noqa: PLC0415

            if sample_name in _on_disc_mock.filenames:
                return

        msg = f"{sample_name} not in available datasets"
        raise KeyError(msg)

    def _validate_index_ranges(
        self, sample_name: str, input_index_ranges: list[tuple[int, int] | None]
    ) -> tuple[
        list[tuple[int, int]], list[tuple[float, float]], dict[str, Any], dict[str, Any]
    ]:

        self._require_sample(sample_name)
        edax_ds = self.ph.load_edax(sample_name)

        valid_index_ranges: list[tuple[int, int]] = []
        physical_ranges: list[tuple[float, float]] = []
        for index_id, index_range in enumerate(input_index_ranges):
            valid_range: tuple[int, int]
            if index_range is None:
                valid_range = (0, edax_ds.axes_by_index[index_id].size)
            else:
                valid_range = (index_range[0], index_range[1])
            valid_index_ranges.append(valid_range)
            physical_ranges.append(
                edax_ds.axis_range(index_id, valid_range[0], valid_range[1])
            )

        md = _make_serializeable_dict(edax_ds.metadata)
        orig_md = _make_serializeable_dict(edax_ds.original_metadata)

        return valid_index_ranges, physical_ranges, md, orig_md

    def get_sample_axes(self, sample_name: str) -> list[EDAX_axis]:
        self._require_sample(sample_name)
        edax_ds = self.ph.load_edax(sample_name)
        return edax_ds.axes.copy()

    def get_single_image(
        self,
        sample_name: str,
        channel_index: int | tuple[int, int],
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
    ) -> raveledImage:
        im = self.get_image(
            sample_name,
            channel_index=channel_index,
            index0_range=index0_range,
            index1_range=index1_range,
        )

        shp = im.shape
        im = im.ravel().tolist()
        return raveledImage(image=im, shape=shp)

    def get_image(
        self,
        sample_name: str,
        channel_index: int | tuple[int, int],
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
    ) -> npt.NDArray[np.int64]:

        self._require_sample(sample_name)
        input_index_ranges = [index0_range, index1_range]
        valid_index_ranges, _, _, _ = self._validate_index_ranges(
            sample_name, input_index_ranges
        )

        channel_slice: int | slice
        if isinstance(channel_index, tuple):
            channel_slice = slice(channel_index[0], channel_index[1])
        elif isinstance(channel_index, int):
            channel_slice = channel_index
        else:
            msg = f"unexpected type for channel_index: must be int or (int, int), but {channel_index=}"  # type:ignore[unreachable]
            raise TypeError(msg)

        edax_ds = self.ph.load_edax(sample_name)
        im_subset: npt.NDArray[np.int64] = (
            edax_ds.data[
                slice(valid_index_ranges[0][0], valid_index_ranges[0][1]),
                slice(valid_index_ranges[1][0], valid_index_ranges[1][1]),
                channel_slice,
            ]
            .copy()
            .astype(np.int64)
        )
        return im_subset

    def get_raveled_multi_channel_intensity_image(
        self,
        sample_name: str,
        channel_range: tuple[int, int],
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        chunking_index: int = 0,
        chunksize: int = 32,
    ) -> raveledImage:
        result = self.get_multi_channel_intensity_image(
            sample_name,
            channel_range,
            index0_range=index0_range,
            index1_range=index1_range,
            chunking_index=chunking_index,
            chunksize=chunksize,
        )
        shp = result.shape
        im = result.ravel().tolist()

        return raveledImage(image=im, shape=shp)

    def get_multi_channel_intensity_image(
        self,
        sample_name: str,
        channel_range: tuple[int, int],
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        chunking_index: int = 0,
        chunksize: int = 32,
    ) -> npt.NDArray[np.int64]:

        self._require_sample(sample_name)
        input_index_ranges = [index0_range, index1_range]
        valid_index_ranges, _, _, _ = self._validate_index_ranges(
            sample_name, input_index_ranges
        )
        index_ranges = [valid_index_ranges[0], valid_index_ranges[1], channel_range]

        orig_ranges = index_ranges.copy()

        shapes_by_dim = [indx[1] - indx[0] for indx in index_ranges]
        final_shape: tuple[int, int] = (shapes_by_dim[0], shapes_by_dim[1])

        index_offsets = [indx[0] for indx in index_ranges[:-1]]
        im_output = np.zeros(final_shape, dtype=int)

        assert im_output.ndim == 2

        i_chunk_0 = orig_ranges[chunking_index][0]
        while i_chunk_0 < orig_ranges[chunking_index][1]:
            i_chunk_1 = i_chunk_0 + chunksize
            i_chunk_1 = min(i_chunk_1, orig_ranges[chunking_index][1])

            index_ranges[chunking_index] = (i_chunk_0, i_chunk_1)

            im = self.get_image(
                sample_name,
                index_ranges[2],
                index0_range=index_ranges[0],
                index1_range=index_ranges[1],
            )

            im_subset = im.sum(axis=-1)

            # find the indices to put it in
            slcs = [
                slice(
                    index_ranges[idim][0] - index_offsets[idim],
                    index_ranges[idim][1] - index_offsets[idim],
                )
                for idim in range(2)
            ]
            im_output[slcs[0], slcs[1]] = im_output[slcs[0], slcs[1]] + im_subset

            i_chunk_0 += chunksize

        return im_output

    def get_spectrum(
        self,
        sample_name: str,
        channel_range: tuple[int, int] | None = None,
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        chunking_index: int = 0,
        chunksize: int = 32,
    ) -> Spectrum1d:

        self._require_sample(sample_name)
        input_index_ranges = [index0_range, index1_range, channel_range]
        valid_index_ranges, physical_ranges, md, md_orig = self._validate_index_ranges(
            sample_name, input_index_ranges
        )
        index_ranges = [
            valid_index_ranges[0],
            valid_index_ranges[1],
            valid_index_ranges[2],
        ]

        orig_ranges = index_ranges.copy()
        final_shape = (index_ranges[2][1] - index_ranges[2][0],)
        im_output = np.zeros(final_shape, dtype=int)

        assert im_output.ndim == 1

        i_chunk_0 = orig_ranges[chunking_index][0]
        while i_chunk_0 < orig_ranges[chunking_index][1]:
            i_chunk_1 = i_chunk_0 + chunksize
            i_chunk_1 = min(i_chunk_1, orig_ranges[chunking_index][1])

            index_ranges[chunking_index] = (i_chunk_0, i_chunk_1)

            im = self.get_image(
                sample_name,
                index_ranges[2],
                index0_range=index_ranges[0],
                index1_range=index_ranges[1],
            )

            im_reduced = im.sum(axis=0).sum(axis=0)
            assert im_reduced.size == im_output.size
            im_output = im_output + im_reduced

            i_chunk_0 += chunksize

        energy_channel_axis = np.arange(index_ranges[2][0], index_ranges[2][1])
        energy_min, energy_max = physical_ranges[2]

        return Spectrum1d(
            energy=energy_channel_axis,
            intensity=im_output,
            energy_min=energy_min,
            energy_max=energy_max,
            metadata=md,
            original_metadata=md_orig,
        )

    def get_refined_metadata(self, sample_name: str) -> MetadataModel:
        self._require_sample(sample_name)
        fl = self.ph.load_edax(sample_name)
        return fl.refined_metadata

    def get_combined_metadata(self, sample_name: str) -> CombinedMetadata:
        self._require_sample(sample_name)
        fl = self.ph.load_edax(sample_name)
        mm = fl.refined_metadata

        axes = fl.axes_by_index
        shp = fl.data.shape
        assert len(shp) == 3

        return CombinedMetadata(metadata=mm, axes_by_index=axes, data_shape=shp)
