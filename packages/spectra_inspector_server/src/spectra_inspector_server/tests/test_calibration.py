from dataclasses import asdict

import numpy as np
import pytest

from spectra_inspector_server.calibration import (
    CalibrationWeights,
    calculate_weights,
    calibration_elements,
    element_energy_ranges_keV,
    sum_in_range,
)


@pytest.fixture
def energy() -> np.ndarray:
    return np.array(
        [
            1.00,
            1.20,
            1.50,
            1.70,
            2.00,
            3.30,
            3.70,
            4.50,
            6.40,
            14.50,
        ],
        dtype=np.float64,
    )


@pytest.fixture
def intensity() -> np.ndarray:
    return np.array(
        [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        dtype=np.int64,
    )


@pytest.fixture
def weights(
    intensity: np.ndarray,
    energy: np.ndarray,
) -> CalibrationWeights:
    return calculate_weights(intensity, energy)


def test_sum_in_range_without_shift() -> None:
    energy = np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float64)
    intensity = np.array([1, 2, 3, 4], dtype=np.int64)

    assert (
        sum_in_range(
            intensity,
            energy,
            1.0,
            2.0,
            apply_shift=False,
        )
        == 5.0
    )


def test_sum_in_range_with_shift() -> None:
    energy = np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float64)
    intensity = np.array([1, 2, 4, 1], dtype=np.int64)

    # Counts in range: [2, 4]
    # Baseline = (2 + 4) / 2 = 3
    # Shifted = [-1, 1]
    # Sum = 0
    assert sum_in_range(intensity, energy, 1.0, 2.0) == pytest.approx(0.0)


def test_sum_in_range_single_bin_is_zero_after_shift() -> None:
    energy = np.array([0.0, 1.0, 2.0], dtype=np.float64)
    intensity = np.array([5, 10, 15], dtype=np.int64)

    assert sum_in_range(intensity, energy, 1.0, 1.0) == pytest.approx(0.0)


def test_sum_in_range_empty_range_raises() -> None:
    energy = np.array([1.0, 2.0], dtype=np.float64)
    intensity = np.array([1, 2], dtype=np.int64)

    with pytest.raises(ValueError, match="No channels"):
        sum_in_range(intensity, energy, 10.0, 11.0)


def test_calculate_weights_returns_dataclass(
    weights: CalibrationWeights,
) -> None:
    assert isinstance(weights, CalibrationWeights)


def test_calculate_weights_total_count(
    weights: CalibrationWeights,
    intensity: np.ndarray,
) -> None:
    assert weights.total_count == float(intensity.sum())
    assert weights.counts_14_15_kev == 100.0
    assert weights.DH_assessment == pytest.approx(100 / intensity.sum())


def test_calculate_weights_contains_all_fields(
    weights: CalibrationWeights,
) -> None:
    fields = asdict(weights)

    expected = set(calibration_elements) | {
        "total_count",
        "counts_14_15_kev",
        "DH_assessment",
    }

    assert set(fields) == expected


@pytest.mark.parametrize("element", calibration_elements)
def test_each_element_weight_matches_sum_in_range(
    element: str,
    weights: CalibrationWeights,
    intensity: np.ndarray,
    energy: np.ndarray,
) -> None:
    e0, e1 = element_energy_ranges_keV[element]

    expected = sum_in_range(intensity, energy, e0, e1) / intensity.sum()

    assert getattr(weights, element) == pytest.approx(expected)


def test_calibration_element_ranges_exist() -> None:
    missing = set(calibration_elements) - element_energy_ranges_keV.keys()

    assert not missing


def test_energy_ranges_are_valid() -> None:
    for element, (e0, e1) in element_energy_ranges_keV.items():
        assert e0 < e1, f"Invalid energy range for {element}"


def test_energy_ranges_do_not_overlap() -> None:
    ranges = [
        (element, *element_energy_ranges_keV[element])
        for element in calibration_elements
    ]

    for idx in range(len(ranges) - 1):
        el1, start1, end1 = ranges[idx]
        el2, start2, end2 = ranges[idx + 1]

        assert end1 < start2, (
            f"Energy ranges overlap: {el1} ({start1}, {end1}) "
            f"and {el2} ({start2}, {end2})"
        )


def test_calibration_elements_are_ordered_by_energy_range() -> None:
    start_energies = [
        element_energy_ranges_keV[element][0] for element in calibration_elements
    ]

    for idx in range(len(start_energies) - 1):
        assert start_energies[idx] < start_energies[idx + 1], (
            f"Calibration elements are not ordered by increasing energy range: "
            f"{calibration_elements[idx]} starts at {start_energies[idx]} keV, "
            f"but {calibration_elements[idx + 1]} starts at "
            f"{start_energies[idx + 1]} keV"
        )


def test_calibration_weights_is_immutable(
    weights: CalibrationWeights,
) -> None:
    with pytest.raises(AttributeError):
        # following typing ignore is due to
        # error: Property "total_count" defined in "CalibrationWeights" is read-only
        # but that is what we are checking...
        weights.total_count = 200.0  # type: ignore[misc]
