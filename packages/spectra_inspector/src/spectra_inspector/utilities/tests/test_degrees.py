import numpy as np
import pytest

from spectra_inspector.utilities import degrees as deg


@pytest.mark.parametrize("dec_deg", np.linspace(-180, 360, 20))
def test_decimal_degrees_roundtrip(dec_deg: float) -> None:
    assert (
        dec_deg
        == deg.DecimalDegrees(dec_deg).to_degrees_min_s().to_decimal_degrees().value()
    )


def test_bad_cases() -> None:

    with pytest.raises(
        ValueError, match="Degrees cannot be negative when cardinal_str is 'S' or 'W'"
    ):
        deg.DecimalDegrees(-100, cardinal_str="W")

    with pytest.raises(
        ValueError, match="Degrees cannot be negative when cardinal_str is 'S' or 'W'"
    ):
        deg.DecimalDegrees(-50, cardinal_str="S")

    with pytest.raises(ValueError, match="Seconds are not in valid range"):
        deg.DegreesMinsSecs(100.0, 10.0, 100.125)

    with pytest.raises(ValueError, match="Minutes are not in valid range"):
        deg.DegreesMinsSecs(100.0, 100.0, 10.1)

    with pytest.raises(ValueError, match="Degrees must be in range"):
        deg.DegreesMinsSecs(460.0, 30.0, 10.1)

    with pytest.raises(ValueError, match="Degrees must be in range"):
        deg.DegreesMinsSecs(-460.0, 30.0, 10.1)


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_lat(sign: float) -> None:
    l1 = deg.Latitude(50 * sign, "N")
    l2 = deg.Latitude(deg.DecimalDegrees(50 * sign, cardinal_str="N"))
    l3 = deg.Latitude(deg.DegreesMinsSecs(50 * sign, 0, 0, cardinal_str="N"))

    assert l1.decimal_degrees.value() == l2.decimal_degrees.value()
    assert l1.decimal_degrees.value() == l3.decimal_degrees.value()

    l1.decimal_degrees = deg.DecimalDegrees(25 * sign, cardinal_str="N")
    assert l1.decimal_degrees.value() == l1.degrees.to_decimal_degrees().value()

    l1.degrees = deg.DegreesMinsSecs(25, 10, 12.3, cardinal_str="N")
    assert l1.decimal_degrees.value() == l1.degrees.to_decimal_degrees().value()


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_lon(sign: float) -> None:
    l1 = deg.Longitude(50 * sign, "E")
    l2 = deg.Longitude(deg.DecimalDegrees(50 * sign, cardinal_str="E"))
    l3 = deg.Longitude(deg.DegreesMinsSecs(50 * sign, 0, 0, cardinal_str="E"))

    assert l1.decimal_degrees.value() == l2.decimal_degrees.value()
    assert l1.decimal_degrees.value() == l3.decimal_degrees.value()

    l1.decimal_degrees = deg.DecimalDegrees(25 * sign, cardinal_str="E")
    assert l1.decimal_degrees.value() == l1.degrees.to_decimal_degrees().value()

    l1.degrees = deg.DegreesMinsSecs(25, 10, 12.3, cardinal_str="E")
    assert l1.decimal_degrees.value() == l1.degrees.to_decimal_degrees().value()


def test_bad_latlon() -> None:
    with pytest.raises(
        ValueError, match="Degrees cannot be negative when cardinal_str is 'S' or 'W'"
    ):
        deg.Longitude(-50, "W")

    with pytest.raises(
        ValueError, match="Degrees cannot be negative when cardinal_str is 'S' or 'W'"
    ):
        deg.Latitude(-50, "S")

    with pytest.raises(ValueError, match="Latitude cardinal_str must be one of"):
        deg.Latitude(50, "W")

    with pytest.raises(ValueError, match="Longitude cardinal_str must be one of"):
        deg.Longitude(50, "N")
