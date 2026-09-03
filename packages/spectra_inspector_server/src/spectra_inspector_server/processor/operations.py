"""Reductions of on-disk EDAX datasets into serializeable results.

Every public method of :class:`OperationEDAXStateHandler` is dispatched by name
off the request queue in ``main.py`` (``queueOpsItem.ops_func``), so a rename
here is a change to how endpoints call in.
"""

from typing import Any

import numpy as np
import numpy.typing as npt

from spectra_inspector_server._file_tree_handling import EDAXPathHandler
from spectra_inspector_server.model import (
    CombinedMetadata,
    EDAX_axis,
    EDAX_raw_ds,
    MetadataModel,
    Spectrum1d,
    raveledImage,
)
from spectra_inspector_server.processor._reductions import (
    accumulator_dtype,
    chunk_bounds,
    fast_accumulator_limit,
)
from spectra_inspector_server.processor.utilities import _make_serializeable_dict

_DEFAULT_CHUNKSIZE = 128


class OperationEDAXStateHandler:
    """Loads EDAX datasets on demand and reduces them for the API.

    Parameters
    ----------
    ph : EDAXPathHandler
        the path handler owning the database of available filesets
    allow_mock_files : bool, optional
        if True, the synthetic samples defined in ``_testing`` are accepted
        alongside those in the database, by default False. Only enabled when
        running under pytest.
    """

    def __init__(self, ph: EDAXPathHandler, allow_mock_files: bool = False) -> None:
        self.ph = ph
        self._allow_mock_files = allow_mock_files

    def _require_sample(self, sample_name: str) -> None:
        """Check that a sample can be loaded, raising if it cannot.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)

        Raises
        ------
        KeyError
            If the sample is in neither the database nor, when mock files are
            allowed, the set of synthetic test samples.
        """

        if sample_name in self.ph.database.available_maps:
            return

        if self._allow_mock_files:
            from spectra_inspector_server._testing import _on_disc_mock  # noqa: PLC0415

            if sample_name in _on_disc_mock.filenames:
                return

        msg = f"{sample_name} not in available datasets"
        raise KeyError(msg)

    def _load(self, sample_name: str, metadata_only: bool = False) -> EDAX_raw_ds:
        self._require_sample(sample_name)
        return self.ph.load_edax(sample_name, metadata_only=metadata_only)

    def _cube(self, sample_name: str, edax_ds: EDAX_raw_ds) -> npt.NDArray[np.int64]:
        if edax_ds.data is None:
            msg = f"data is None for sample {sample_name}"
            raise ValueError(msg)
        return edax_ds.data

    @staticmethod
    def _index_ranges(
        edax_ds: EDAX_raw_ds, input_index_ranges: list[tuple[int, int] | None]
    ) -> tuple[list[tuple[int, int]], list[tuple[float, float]]]:

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

        return valid_index_ranges, physical_ranges

    def _validate_index_ranges(
        self, sample_name: str, input_index_ranges: list[tuple[int, int] | None]
    ) -> tuple[
        list[tuple[int, int]], list[tuple[float, float]], dict[str, Any], dict[str, Any]
    ]:
        """Fill in unspecified index ranges and collect a sample's metadata.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)
        input_index_ranges : list[tuple[int, int] | None]
            the (start, stop) index ranges to validate, ordered by axis. A
            None entry is replaced by the full extent of that axis.

        Returns
        -------
        tuple[list[tuple[int, int]], list[tuple[float, float]], dict, dict]
            ``(index_ranges, physical_ranges, metadata, original_metadata)``:
            the filled-in index ranges, the physical values those indices map
            to via the axis scaling, and serializeable copies of the dataset's
            two metadata dictionaries.
        """
        edax_ds = self._load(sample_name)
        valid_index_ranges, physical_ranges = self._index_ranges(
            edax_ds, input_index_ranges
        )

        md = _make_serializeable_dict(edax_ds.metadata)
        orig_md = _make_serializeable_dict(edax_ds.original_metadata)

        return valid_index_ranges, physical_ranges, md, orig_md

    def get_sample_axes(self, sample_name: str) -> list[EDAX_axis]:
        """The axis descriptions of a sample.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)

        Returns
        -------
        list[EDAX_axis]
            a copy of the axes, ordered as they are in the data array:
            (index0, index1, energy channel).
        """
        return self._load(sample_name).axes.copy()

    def get_single_image(
        self,
        sample_name: str,
        channel_index: int | tuple[int, int],
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
    ) -> raveledImage:
        """A single-channel image of a sample, flattened for transport.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)
        channel_index : int | tuple[int, int]
            the energy channel to image. A (start, stop) tuple selects a
            channel slice without reducing it, which yields a 3D result that
            ``raveledImage`` cannot describe -- callers pass a single index.
        index0_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 0, by default None, which
            uses the full axis.
        index1_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 1, by default None, which
            uses the full axis.

        Returns
        -------
        raveledImage
            the flattened image and the shape needed to restore it.
        """
        im = self.get_image(
            sample_name,
            channel_index=channel_index,
            index0_range=index0_range,
            index1_range=index1_range,
        )

        shp = im.shape
        im1d = im.ravel().tolist()
        return raveledImage(image=im1d, shape=shp)

    def get_image(
        self,
        sample_name: str,
        channel_index: int | tuple[int, int],
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        edax_ds: Any | None = None,
    ) -> npt.NDArray[np.int64]:
        """A subset of a sample's data cube.

        The subset is sliced straight out of the memory mapped ``.spd``
        payload, so only the requested portion is read from disk.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)
        channel_index : int | tuple[int, int]
            a single energy channel, or a (start, stop) channel range to keep
            as an axis of the result.
        index0_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 0, by default None, which
            uses the full axis.
        index1_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 1, by default None, which
            uses the full axis.
        edax_ds : Any | None, optional
            an already loaded ``EDAX_raw_ds`` to slice, by default None, in
            which case the sample is loaded here. Chunked callers pass one in
            to avoid re-loading the dataset for every chunk.

        Returns
        -------
        npt.NDArray[np.int64]
            the subset, of shape (n_index0, n_index1) for an integer
            ``channel_index`` or (n_index0, n_index1, n_channels) for a range.

        Raises
        ------
        TypeError
            If ``channel_index`` is neither an int nor a pair of ints.
        ValueError
            If the loaded dataset carries no data array.
        """

        if edax_ds is None:
            edax_ds = self._load(sample_name)
        else:
            self._require_sample(sample_name)

        valid_index_ranges, _ = self._index_ranges(
            edax_ds, [index0_range, index1_range]
        )

        channel_slice: int | slice
        if isinstance(channel_index, tuple):
            channel_slice = slice(channel_index[0], channel_index[1])
        elif isinstance(channel_index, int):
            channel_slice = channel_index
        else:
            msg = f"unexpected type for channel_index: must be int or (int, int), but {channel_index=}"  # type:ignore[unreachable]
            raise TypeError(msg)

        im_subset: npt.NDArray[np.int64] = self._cube(sample_name, edax_ds)[
            slice(valid_index_ranges[0][0], valid_index_ranges[0][1]),
            slice(valid_index_ranges[1][0], valid_index_ranges[1][1]),
            channel_slice,
        ]
        return im_subset

    def get_raveled_multi_channel_intensity_image(
        self,
        sample_name: str,
        channel_range: tuple[int, int],
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        chunking_index: int = 0,
        chunksize: int = _DEFAULT_CHUNKSIZE,
    ) -> raveledImage:
        """An intensity image summed over a channel range, flattened for transport.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)
        channel_range : tuple[int, int]
            the (start, stop) energy channel range to sum over
        index0_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 0, by default None, which
            uses the full axis.
        index1_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 1, by default None, which
            uses the full axis.
        chunking_index : int, optional
            the spatial axis (0 or 1) to chunk the summation over, by default 0
        chunksize : int, optional
            number of elements of ``chunking_index`` per chunk, by default 128

        Returns
        -------
        raveledImage
            the flattened image and the shape needed to restore it.
        """
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
        chunksize: int = _DEFAULT_CHUNKSIZE,
    ) -> npt.NDArray[np.int64]:
        """Sum a sample's data cube over a range of energy channels.

        The summation is chunked along one spatial axis so that the full cube
        is never held in memory at once.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)
        channel_range : tuple[int, int]
            the (start, stop) energy channel range to sum over
        index0_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 0, by default None, which
            uses the full axis.
        index1_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 1, by default None, which
            uses the full axis.
        chunking_index : int, optional
            the spatial axis (0 or 1) to chunk the summation over, by default 0
        chunksize : int, optional
            number of elements of ``chunking_index`` per chunk, by default 128

        Returns
        -------
        npt.NDArray[np.int64]
            the summed intensity image, of shape (n_index0, n_index1).

        Raises
        ------
        ValueError
            If the loaded dataset carries no data array.
        """

        edax_ds = self._load(sample_name)
        data = self._cube(sample_name, edax_ds)
        valid_index_ranges, _ = self._index_ranges(
            edax_ds, [index0_range, index1_range]
        )
        index_ranges = [valid_index_ranges[0], valid_index_ranges[1], channel_range]

        shapes_by_dim = [indx[1] - indx[0] for indx in index_ranges]
        final_shape: tuple[int, int] = (shapes_by_dim[0], shapes_by_dim[1])
        im_output = np.zeros(final_shape, dtype=np.int64)
        assert im_output.ndim == 2

        acc_dtype = accumulator_dtype(data.dtype, shapes_by_dim[2])

        # prepare channel slice once
        channel_slice = slice(channel_range[0], channel_range[1])

        for chunk in chunk_bounds(*index_ranges[chunking_index], chunksize):
            slices = [
                slice(*index_ranges[0]),
                slice(*index_ranges[1]),
                channel_slice,
            ]
            slices[chunking_index] = slice(*chunk)
            out_slices = tuple(
                slice(
                    slices[idim].start - index_ranges[idim][0],
                    slices[idim].stop - index_ranges[idim][0],
                )
                for idim in range(2)
            )
            # sum directly from the memmap along the channel axis, into an
            # accumulator narrow enough to stay on numpy's fast reduce loop.
            im_output[out_slices] += np.sum(
                data[tuple(slices)], axis=-1, dtype=acc_dtype
            )
        return im_output

    def get_spectrum(
        self,
        sample_name: str,
        channel_range: tuple[int, int] | None = None,
        index0_range: tuple[int, int] | None = None,
        index1_range: tuple[int, int] | None = None,
        chunking_index: int = 0,
        chunksize: int = _DEFAULT_CHUNKSIZE,
    ) -> Spectrum1d:
        """Sum a sample's data cube over a spatial region into a 1D spectrum.

        The summation is chunked along one spatial axis so that the full cube
        is never held in memory at once.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)
        channel_range : tuple[int, int] | None, optional
            the (start, stop) energy channel range to return, by default None,
            which uses every channel.
        index0_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 0 to sum over, by default
            None, which uses the full axis.
        index1_range : tuple[int, int] | None, optional
            (start, stop) index range along axis 1 to sum over, by default
            None, which uses the full axis.
        chunking_index : int, optional
            the spatial axis (0 or 1) to chunk the summation over, by default 0
        chunksize : int, optional
            number of elements of ``chunking_index`` per chunk, by default 128

        Returns
        -------
        Spectrum1d
            counts per energy channel over the selected region, carrying the
            channel indices, the physical energy range they span and the
            dataset metadata.
        """

        input_index_ranges = [index0_range, index1_range, channel_range]
        valid_index_ranges, physical_ranges, md, md_orig = self._validate_index_ranges(
            sample_name, input_index_ranges
        )
        index_ranges = [
            valid_index_ranges[0],
            valid_index_ranges[1],
            valid_index_ranges[2],
        ]

        data = self._cube(sample_name, self._load(sample_name))

        final_shape = (index_ranges[2][1] - index_ranges[2][0],)
        im_output = np.zeros(final_shape, dtype=np.int64)

        assert im_output.ndim == 1

        shapes_by_dim = [indx[1] - indx[0] for indx in index_ranges]
        # every chunk sums over both spatial axes, so the number of terms per
        # accumulator element is the chunk length times the un-chunked axis.
        across = shapes_by_dim[1 - chunking_index]
        fast_limit = fast_accumulator_limit(data.dtype) // max(across, 1)
        max_chunk = min(chunksize, fast_limit) if fast_limit >= 1 else chunksize

        chunks = chunk_bounds(*index_ranges[chunking_index], max_chunk)
        longest = max((c[1] - c[0] for c in chunks), default=0)
        acc_dtype = accumulator_dtype(data.dtype, longest * across)

        for chunk in chunks:
            slices = [slice(*rng) for rng in index_ranges]
            slices[chunking_index] = slice(*chunk)
            partial = np.sum(data[tuple(slices)], axis=(0, 1), dtype=acc_dtype)
            assert partial.size == im_output.size
            im_output += partial

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
        """The structured metadata of a sample, read without loading its data.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)

        Returns
        -------
        MetadataModel
            the subset of the EDAX metadata the API exposes.
        """
        return self._load(sample_name, metadata_only=True).refined_metadata

    def get_combined_metadata(self, sample_name: str) -> CombinedMetadata:
        """The metadata, axes and data shape of a sample.

        Unlike :meth:`get_refined_metadata` this opens the ``.spd`` payload,
        since the data shape comes from the array itself.

        Parameters
        ----------
        sample_name : str
            the sample name (the basename shared by an EDAX fileset)

        Returns
        -------
        CombinedMetadata
            the refined metadata, the axes keyed by their position in the
            array and the (index0, index1, channel) shape of the data.

        Raises
        ------
        ValueError
            If the loaded dataset carries no data array.
        """
        fl = self._load(sample_name)
        mm = fl.refined_metadata

        axes = fl.axes_by_index
        shp = self._cube(sample_name, fl).shape
        assert len(shp) == 3

        return CombinedMetadata(metadata=mm, axes_by_index=axes, data_shape=shp)
