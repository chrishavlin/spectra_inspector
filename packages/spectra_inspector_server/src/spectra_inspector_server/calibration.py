from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

type CalibrationElement = Literal["Na", "Mg", "Al", "Si", "P", "K", "Ca", "Ti", "Fe"]


@dataclass(frozen=True, slots=True)
class CalibrationWeights:
    Na: float
    Mg: float
    Al: float
    Si: float
    P: float
    K: float
    Ca: float
    Ti: float
    Fe: float

    total_count: float
    counts_14_15_kev: float
    DH_assessment: float

    def todict(self) -> dict[str, Any]:
        return asdict(self)


element_energy_ranges_keV: dict[str, tuple[float, float]] = {
    "Na": (0.96, 1.12),
    "Mg": (1.13, 1.34),
    "Al": (1.40, 1.61),
    "Si": (1.645, 1.88),
    "P": (1.905, 2.10),
    "K": (3.235, 3.47),
    "Ca": (3.57, 3.84),
    "Ti": (4.415, 4.66),
    "Fe": (6.275, 6.54),
}

calibration_elements: tuple[CalibrationElement, ...] = (
    "Na",
    "Mg",
    "Al",
    "Si",
    "P",
    "K",
    "Ca",
    "Ti",
    "Fe",
)

# Ensure all calibration elements have defined energy ranges.
missing = set(calibration_elements) - element_energy_ranges_keV.keys()
if missing:
    msg = f"Missing energy ranges for calibration elements: {sorted(missing)}"
    raise ValueError(msg)


def sum_in_range(
    intensity: npt.NDArray[np.int64],
    energy_keV: npt.NDArray[np.float64],
    e0: float,
    e1: float,
    apply_shift: bool = True,
) -> float:
    mask = (energy_keV >= e0) & (energy_keV <= e1)
    counts = intensity[mask]

    if counts.size == 0:
        msg = f"No channels in energy range [{e0}, {e1}] keV."
        raise ValueError(msg)

    if apply_shift:
        baseline = (counts[0] + counts[-1]) / 2
        return float(np.sum(counts - baseline))

    return float(np.sum(counts))


def calculate_weights(
    intensity: npt.NDArray[np.int64],
    energy_keV: npt.NDArray[np.float64],
) -> CalibrationWeights:
    total_count = float(np.sum(intensity))
    counts_14_15_kev = sum_in_range(
        intensity,
        energy_keV,
        14.0,
        15.005,
        apply_shift=False,
    )

    element_weights: dict[CalibrationElement, float] = {}

    for el in calibration_elements:
        e0, e1 = element_energy_ranges_keV[el]
        weight = sum_in_range(intensity, energy_keV, e0, e1) / total_count
        # the baseline subtraction in sum_in_range leaves a small or negative
        # sum for an element that is absent; report those as exactly zero.
        element_weights[el] = weight if weight > 0 else 0.0

    return CalibrationWeights(
        Na=element_weights["Na"],
        Mg=element_weights["Mg"],
        Al=element_weights["Al"],
        Si=element_weights["Si"],
        P=element_weights["P"],
        K=element_weights["K"],
        Ca=element_weights["Ca"],
        Ti=element_weights["Ti"],
        Fe=element_weights["Fe"],
        total_count=total_count,
        counts_14_15_kev=counts_14_15_kev,
        DH_assessment=counts_14_15_kev / total_count,
    )
