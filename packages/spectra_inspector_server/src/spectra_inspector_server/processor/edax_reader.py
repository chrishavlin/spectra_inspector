import struct
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from spectra_inspector_server.model import EDAX_file_set, EDAX_raw_ds


def parse_spc_file(spc_path: Path) -> dict[str, Any]:
    """
    Parses all documented metadata and structural parameters from a binary EDAX
    .spc (SPECTRUM-V70) file to preserve full processing history and provenance.
    """
    with open(spc_path, "rb") as f:
        b = f.read()

    # Offset 0-40: Basic File Layout & Structural Details
    f_version = struct.unpack_from("<f", b, 0)[0]
    a_version = struct.unpack_from("<f", b, 4)[0]
    file_name = b[8:16].decode("ascii", errors="ignore").strip("\x00 ")

    # Dates & Times (Offset 16, 20)
    day, month, year, year_type = struct.unpack_from("<4B", b, 16)
    hour, minute, second, hundredths = struct.unpack_from("<4B", b, 20)
    collect_date = f"{year_type * 100 + year:04d}-{month:02d}-{day:02d}"
    collect_time = f"{hour:02d}:{minute:02d}:{second:02d}.{hundredths:02d}"

    file_size = struct.unpack_from("<i", b, 24)[0]
    data_start = struct.unpack_from("<i", b, 28)[0]
    num_pts = struct.unpack_from("<h", b, 32)[0]
    intersect_dist = (
        struct.unpack_from("<h", b, 34)[0] / 100.0
    )  # converted from *100 mm
    working_dist = struct.unpack_from("<h", b, 36)[0] / 100.0  # converted from *100 mm
    scale_setting = struct.unpack_from("<h", b, 38)[0] / 100.0  # converted from *100 mm

    # Offset 40-100: Microscope and Image settings
    magnification = struct.unpack_from("<i", b, 40)[0]
    tilt_angle = struct.unpack_from("<h", b, 44)[0] / 10.0  # converted from *10 deg
    take_off = struct.unpack_from("<h", b, 46)[0] / 10.0  # converted from *10 deg
    sec_tc = struct.unpack_from("<h", b, 48)[0]
    num_scans = struct.unpack_from("<h", b, 50)[0]
    sc_rate = struct.unpack_from("<h", b, 52)[0]
    b_width = struct.unpack_from("<h", b, 54)[0]
    b_height = struct.unpack_from("<h", b, 56)[0]
    sc_energy = struct.unpack_from("<h", b, 58)[0]
    spot_size = struct.unpack_from("<h", b, 60)[0]
    sample_id = b[62:94].decode("ascii", errors="ignore").strip("\x00 ")
    det_type = struct.unpack_from("<h", b, 94)[0]
    f_co_type = struct.unpack_from("<h", b, 96)[0]
    f_opt_elem = struct.unpack_from("<h", b, 98)[0]

    # Offset 100-384: Labels & Microanalysis Window Rules
    user_kv = struct.unpack_from("<f", b, 100)[0]
    user_tilt = struct.unpack_from("<f", b, 104)[0]
    user_take_off = struct.unpack_from("<f", b, 108)[0]
    user_mag = struct.unpack_from("<f", b, 112)[0]
    user_wd = struct.unpack_from("<f", b, 116)[0]
    label = b[120:252].decode("ascii", errors="ignore").strip("\x00 ")

    # Elements (Offset 252-316: 32 elements maximum, 2 bytes per symbol)
    elements = []
    for i in range(32):
        off = 252 + (i * 2)
        sym = b[off : off + 2].decode("ascii", errors="ignore").strip("\x00 ")
        if sym:
            elements.append(sym)

    # Window settings rules (Offsets 316-384)
    roi_start_chan = list(struct.unpack_from("<32h", b, 316))
    roi_end_chan = list(struct.unpack_from("<32h", b, 348))
    st_type = struct.unpack_from("<h", b, 380)[0]
    sam_type = struct.unpack_from("<h", b, 382)[0]

    # Offset 384-448: Core Signal Conversions and Spectrum Properties
    ev_per_chan = struct.unpack_from("<i", b, 384)[0]
    be_win_type = struct.unpack_from("<h", b, 388)[0]
    a_coefficient = struct.unpack_from("<f", b, 390)[0]
    raw_peak_intensity = struct.unpack_from("<f", b, 394)[0]
    bk_intensity = struct.unpack_from("<f", b, 398)[0]
    esc_flag = struct.unpack_from("<h", b, 402)[0]
    num_peaks = struct.unpack_from("<h", b, 404)[0]
    # Background options block
    bg_points = {
        "cur_bg_type": struct.unpack_from("<h", b, 406)[0],
        "bg_del_e": struct.unpack_from("<h", b, 408)[0],
        "bg_num_pts": struct.unpack_from("<h", b, 410)[0],
        "bg_pts": list(struct.unpack_from("<24h", b, 412)),
    }
    multi_bare = struct.unpack_from("<h", b, 444)[0]
    z_max = struct.unpack_from("<h", b, 446)[0]

    # Offset 448-548: Physical Calibrations and Angles
    start_energy = struct.unpack_from("<f", b, 448)[0]
    end_energy = struct.unpack_from("<f", b, 452)[0]
    live_time = struct.unpack_from("<f", b, 456)[0]
    preset_time = struct.unpack_from("<f", b, 460)[0]
    dead_time_pct = struct.unpack_from("<f", b, 464)[0]
    serv_time = struct.unpack_from("<f", b, 468)[0]
    det_reso = struct.unpack_from("<f", b, 472)[0]
    det_reso_chan = struct.unpack_from("<i", b, 476)[0]
    par_thick = struct.unpack_from("<f", b, 480)[0]
    al_thick = struct.unpack_from("<f", b, 484)[0]
    be_win_thick = struct.unpack_from("<f", b, 488)[0]
    au_thick = struct.unpack_from("<f", b, 492)[0]
    si_dead_layer = struct.unpack_from("<f", b, 496)[0]
    si_live_layer = struct.unpack_from("<f", b, 500)[0]
    xray_incidence_angle = struct.unpack_from("<f", b, 504)[0]
    azimuth_angle = struct.unpack_from("<f", b, 508)[0]
    elevation_angle = struct.unpack_from("<f", b, 512)[0]
    b_coefficient = struct.unpack_from("<f", b, 516)[0]
    c_coefficient = struct.unpack_from("<f", b, 520)[0]
    tail_max_chan = struct.unpack_from("<f", b, 524)[0]
    tail_height_adj = struct.unpack_from("<f", b, 528)[0]
    acc_voltage_kv = struct.unpack_from("<f", b, 532)[0]
    ap_window_thick = struct.unpack_from("<f", b, 536)[0]
    x_tilt_angle = struct.unpack_from("<f", b, 540)[0]
    y_tilt_angle = struct.unpack_from("<f", b, 544)[0]

    # Consolidate complete structural breakdown matching the document layout
    return {
        "fVersion": f_version,
        "aVersion": a_version,
        "fileName": file_name,
        "collectDate": collect_date,
        "collectTime": collect_time,
        "fileSize": file_size,
        "dataStart": data_start,
        "numPts": num_pts,
        "IntersectingDist": intersect_dist,
        "WorkingDist": working_dist,
        "ScaleSetting": scale_setting,
        "magnification": magnification,
        "tiltAngle": tilt_angle,
        "takeOff": take_off,
        "secTc": sec_tc,
        "numScans": num_scans,
        "scRate": sc_rate,
        "bWidth": b_width,
        "bHeight": b_height,
        "scEnergy": sc_energy,
        "spotSize": spot_size,
        "sampleID": sample_id,
        "detType": det_type,
        "fCoType": f_co_type,
        "fOptElem": f_opt_elem,
        "userKV": user_kv,
        "userTilt": user_tilt,
        "userTakeOff": user_take_off,
        "userMag": user_mag,
        "userWD": user_wd,
        "label": label,
        "elements": elements,
        "roiStartChan": roi_start_chan,
        "roiEndChan": roi_end_chan,
        "stType": st_type,
        "samType": sam_type,
        "evPerChan": ev_per_chan,
        "beWinType": be_win_type,
        "a_coeff": a_coefficient,
        "rawPeakInten": raw_peak_intensity,
        "bkInten": bk_intensity,
        "escFlag": esc_flag,
        "numPeaks": num_peaks,
        "bgOptions": bg_points,
        "multiBare": multi_bare,
        "zMax": z_max,
        "startEnergy": start_energy,
        "endEnergy": end_energy,
        "liveTime": live_time,
        "presetTime": preset_time,
        "deadTimePct": dead_time_pct,
        "servTime": serv_time,
        "detReso": det_reso,
        "detResoChan": det_reso_chan,
        "parThick": par_thick,
        "alThick": al_thick,
        "beWinThick": be_win_thick,
        "auThick": au_thick,
        "siDead": si_dead_layer,
        "siLive": si_live_layer,
        "xray_inc": xray_incidence_angle,
        "azimuth": azimuth_angle,
        "elevation": elevation_angle,
        "b_coeff": b_coefficient,
        "c_coeff": c_coefficient,
        "tail_max": tail_max_chan,
        "tail_height": tail_height_adj,
        "kV": acc_voltage_kv,
        "apThick": ap_window_thick,
        "xTilt": x_tilt_angle,
        "yTilt": y_tilt_angle,
    }


def parse_ipr_file(ipr_path: Path) -> dict[str, Any]:
    """
    Parses all documented metadata fields from a binary EDAX .ipr file
    to preserve complete processing history and spatial provenance.
    """
    with open(ipr_path, "rb") as f:
        binary_data = f.read()

    # Offset 0-34: Dimensions, Layout, Matrix Configuration
    map_type = struct.unpack_from("<h", binary_data, 0)[0]
    n_layers = struct.unpack_from("<h", binary_data, 2)[0]
    n_points = struct.unpack_from("<h", binary_data, 12)[0]  # Number of X points
    n_lines = struct.unpack_from("<h", binary_data, 14)[0]  # Number of Y lines
    n_channels = struct.unpack_from("<h", binary_data, 18)[
        0
    ]  # Number of energy channels
    ev_per_chan = struct.unpack_from("<f", binary_data, 20)[
        0
    ]  # Energy scale (eV per channel)
    preset_time = struct.unpack_from("<i", binary_data, 20)[
        0
    ]  # Preset / Dwell time (ms) overlay
    count_bytes = struct.unpack_from("<h", binary_data, 24)[
        0
    ]  # Bytes per data point (1, 2, or 4)
    data_offset = struct.unpack_from("<i", binary_data, 30)[
        0
    ]  # Data offset payload pointer

    # Offset 34-64: Instrument, Beam, and Collection Angles
    sc_energy = struct.unpack_from("<f", binary_data, 34)[0]  # Beam Energy (kV)
    mag = struct.unpack_from("<f", binary_data, 38)[0]  # Magnification
    samp_tilt = struct.unpack_from("<f", binary_data, 42)[0]  # Stage tilt (Alpha)
    elev_angle = struct.unpack_from("<f", binary_data, 46)[
        0
    ]  # Detector elevation angle
    azim_angle = struct.unpack_from("<f", binary_data, 50)[0]  # Detector azimuth angle
    w_distance = struct.unpack_from("<f", binary_data, 54)[0]  # Working Distance (mm)
    shape_type = struct.unpack_from("<h", binary_data, 58)[0]

    # Offset 64-128: Spatial Microns per Pixel & Dynamic Matrix Transforms
    mpp_x = struct.unpack_from("<f", binary_data, 64)[0]  # Microns per pixel in X
    mpp_y = struct.unpack_from("<f", binary_data, 68)[0]  # Microns per pixel in Y

    # Unpack 3x3 Stage/Scan alignment matrix
    matrix_elements = struct.unpack_from("<9f", binary_data, 72)
    scan_matrix = [list(matrix_elements[i : i + 3]) for i in range(0, 9, 3)]

    # Translation vector mappings
    b_vector = list(struct.unpack_from("<3f", binary_data, 108))

    # Offset 128-192: Atomic Target Element List (32 items max, 2 bytes each)
    elements = []
    for i in range(32):
        start_offset = 128 + (i * 2)
        element_bytes = binary_data[start_offset : start_offset + 2]
        elem_str = element_bytes.decode("ascii", errors="ignore").strip("\x00 ").strip()
        if elem_str:
            elements.append(elem_str)

    # Offset 192-512: Text String Arrays & File Paths
    # Slices match the absolute lengths specified in the ImageIPR spec document
    un_spc_path = binary_data[192:256].decode("ascii", errors="ignore").strip("\x00 ")
    ipr_path_str = binary_data[256:320].decode("ascii", errors="ignore").strip("\x00 ")
    job_path = binary_data[320:384].decode("ascii", errors="ignore").strip("\x00 ")
    sample_id = binary_data[384:448].decode("ascii", errors="ignore").strip("\x00 ")
    operator_id = binary_data[448:512].decode("ascii", errors="ignore").strip("\x00 ")

    # Structuring everything seamlessly into a single provenance bundle
    spd_header = {
        "nPoints": n_points,
        "nLines": n_lines,
        "nChannels": n_channels,
        "countBytes": count_bytes,
        "dataOffset": data_offset,
    }

    return {
        "spd_header": spd_header,
        "mapType": map_type,
        "nLayers": n_layers,
        "ev_per_chan": ev_per_chan,
        "preset_time": preset_time,
        "beam_energy": sc_energy,
        "magnification": mag,
        "tilt_alpha": samp_tilt,
        "elevation_angle": elev_angle,
        "azimuth_angle": azim_angle,
        "workingDistance": w_distance,
        "shapeType": shape_type,
        "mppX": mpp_x,
        "mppY": mpp_y,
        "scanMatrix": scan_matrix,
        "bVector": b_vector,
        "elements": elements,
        "unSpcPath": un_spc_path,
        "iprPath": ipr_path_str,
        "jobPath": job_path,
        "sampleID": sample_id,
        "operatorID": operator_id,
    }


def load_spd_into_memmap(
    header: dict[str, Any], spd_path: Path
) -> npt.NDArray[np.int64]:
    """
    Creates a direct, zero-copy np.memmap pointer into the binary .spd payload.
    Provides thread-safe concurrent read capabilities.
    """
    nx = header["nPoints"]
    ny = header["nLines"]
    nCh = header["nChannels"]
    offset = header["dataOffset"]
    nbytes = str(header["countBytes"])

    data_type = {"1": "u1", "2": "u2", "4": "u4"}[nbytes]

    data = np.memmap(str(spd_path), mode="r", offset=offset, dtype=data_type)

    data = data.squeeze().reshape((nCh, nx, ny), order="F").T
    return data


def build_axes_and_metadata(
    ipr_data: dict[str, Any], spc_data: dict[str, Any], filename: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Builds the standard dictionary structures for 'axes' and 'metadata'
    to feed the EDAX_raw_ds initialization logic, mapping top-level ipr and spc datasets.
    """
    h = ipr_data["spd_header"]

    # Reconstruct axes configuration maps to match (ny, nx, nCh) array layout
    axes = [
        {
            "size": h["nLines"],
            "index_in_array": 0,
            "name": "y",
            "scale": float(ipr_data["mppY"]),
            "offset": 0,
            "units": "um",
            "navigate": True,
        },
        {
            "size": h["nPoints"],
            "index_in_array": 1,
            "name": "x",
            "scale": float(ipr_data["mppX"]),
            "offset": 0,
            "units": "um",
            "navigate": True,
        },
        {
            "size": h["nChannels"],
            "index_in_array": 2,
            "name": "Energy",
            "scale": float(spc_data["evPerChan"])
            / 1000.0,  # Sourced cleanly from flat spc_data
            "offset": float(
                spc_data["startEnergy"]
            ),  # Sourced cleanly from flat spc_data
            "units": "keV",
            "navigate": False,
        },
    ]

    # Map the parsed metadata safely into your nested target schema
    metadata = {
        "General": {
            "original_filename": filename,
            "title": Path(filename).stem,
        },
        "Signal": {
            "signal_type": "EDS",
        },
        "Acquisition_instrument": {
            "SEM": {
                "beam_energy": ipr_data["beam_energy"],
                "Stage": {
                    "tilt_alpha": ipr_data["tilt_alpha"],
                },
                "Detector": {
                    "EDS": {
                        "azimuth_angle": ipr_data["azimuth_angle"],
                        "elevation_angle": ipr_data["elevation_angle"],
                        "energy_resolution_MnKa": float(
                            spc_data["detReso"]
                        ),  # Sourced from flat spc_data
                        "live_time": float(
                            spc_data["liveTime"]
                        ),  # Sourced from flat spc_data
                    }
                },
            }
        },
        "Sample": {
            "elements": ipr_data["elements"],
        },
    }

    return axes, metadata


def load_edax_spd(
    edax_files: EDAX_file_set, metadata_only: bool = False
) -> EDAX_raw_ds:
    """
    Alternative pure-Python drop-in replacement for loading EDAX data models
    without using the rsciio library dependency.
    """
    # 1. Parse both binary headers completely flat
    ipr_data = parse_ipr_file(edax_files.ipr)
    spc_data = parse_spc_file(edax_files.spc)

    # 2. Package matching structural components using both dictionaries
    axes_list, metadata_dict = build_axes_and_metadata(
        ipr_data, spc_data, edax_files.spd.name
    )

    # Restructure original_metadata into clean top-level sibling keys
    raw_ds_payload = {
        "axes": axes_list,
        "metadata": metadata_dict,
        "original_metadata": {
            "ipr_header": ipr_data,
            "spc_header": spc_data,
        },
    }

    if metadata_only:
        return EDAX_raw_ds(raw_ds_payload)

    # 3. Add low-overhead concurrent-safe data payload mapping
    data = load_spd_into_memmap(ipr_data["spd_header"], edax_files.spd)
    raw_ds_payload["data"] = data

    return EDAX_raw_ds(raw_ds_payload)
