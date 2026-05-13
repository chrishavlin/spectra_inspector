from typing import Literal

import numpy as np


class DegreesMinsSecs:
    cardinal_str: Literal["N", "S", "E", "W"] | None

    def __init__(
        self,
        degs: float,
        mins: float,
        sec: float,
        sec_precision: int = 2,
        cardinal_str: Literal["N", "S", "E", "W"] | None = None,
    ):
        self.degs = int(degs)
        self.mins = int(mins)
        self.sec = sec
        self.sec_precision = sec_precision
        self.cardinal_str = cardinal_str
        self._validate()

    def to_decimal_degrees(self) -> "DecimalDegrees":
        sign = np.sign(self.degs)
        return DecimalDegrees(
            sign * (np.abs(self.degs) + self.mins / 60 + self.sec / 3600)
        )

    def to_str(self) -> str:
        # looks like: 50°56'07.2"S or 72°59'40.9"W
        s = np.round(self.sec, self.sec_precision)
        card = self.cardinal_str or ""
        s_str = str(s).zfill(4)
        return f"{self.degs}\N{DEGREE SIGN}{str(self.mins).zfill(2)}'{s_str}\"{card}"

    @staticmethod
    def from_decimal(
        decimal_degree: "float | int | DecimalDegrees",
    ) -> "DegreesMinsSecs":
        if isinstance(decimal_degree, (float, int)):
            return DecimalDegrees(decimal_degree).to_degrees_min_s()
        return decimal_degree.to_degrees_min_s()

    def __repr__(self) -> str:
        return self.to_str()

    def _validate(self) -> None:
        if self.mins > 60 or self.mins < 0:
            msg = f"Minutes are not in valid range (0, 60): {self.mins}. Full coordinate: {self.to_str()}"
            raise ValueError(msg)

        if self.sec > 60 or self.sec < 0:
            msg = f"Seconds are not in valid range (0, 60): {self.sec}. Full coordinate: {self.to_str()}"
            raise ValueError(msg)

        if np.abs(self.degs) > 360:
            msg = f"Degrees must be in range (-360, 360): {self.degs}. Full coordinate: {self.to_str()}"
            raise ValueError(msg)

        if self.cardinal_str == "E" and self.degs < -180:
            msg = f"When cardinal_str is 'E', degrees cannot be < -180: {self.degs}. Full coordinate: {self.to_str()}"
            raise ValueError(msg)

        if self.cardinal_str == "N" and np.abs(self.degs) > 90:
            msg = f"When cardinal_str is 'N', degrees must be in range (-90, 90): {self.degs}. Full coordinate: {self.to_str()}"
            raise ValueError(msg)


class DecimalDegrees:
    cardinal_str: Literal["N", "S", "E", "W"] | None

    def __init__(
        self,
        decimal_degree: float,
        cardinal_str: Literal["N", "S", "E", "W"] | None = None,
    ) -> None:
        self.decimal_degree = decimal_degree
        self.cardinal_str = cardinal_str
        self._validate()

    def to_degrees_min_s(self) -> DegreesMinsSecs:
        sign = np.sign(self.decimal_degree)
        abs_deg = np.abs(self.decimal_degree)
        deg = np.floor(abs_deg)
        mins_sec = (abs_deg - deg) * 60
        mins = np.floor(mins_sec)
        sec = (mins_sec - mins) * 60
        return DegreesMinsSecs(sign * deg, mins, sec, cardinal_str=self.cardinal_str)

    def __repr__(self) -> str:
        card = self.cardinal_str or ""
        return str(self.decimal_degree) + "\N{DEGREE SIGN}" + card

    def value(self) -> float:
        return self.decimal_degree

    def _validate(self) -> None:
        if self.decimal_degree > 360:
            msg = f"Degrees cannot be greater than 360: {self.decimal_degree}"
            raise ValueError(msg)

        if self.decimal_degree < 0 and self.cardinal_str in ("S", "W"):
            msg = f"Degrees cannot be negative when cardinal_str is 'S' or 'W': {self.decimal_degree=}, {self.cardinal_str=}"
            raise ValueError(msg)


class _LatLonBase:
    _decimal_degrees: DecimalDegrees
    _degrees: DegreesMinsSecs

    def __init__(
        self,
        degrees: DecimalDegrees | DegreesMinsSecs | float,
        cardinal_str: Literal["N", "S", "E", "W"] | None = None,
    ) -> None:

        if isinstance(degrees, (float, int)):
            if cardinal_str is None:
                msg = f"Could not infer cardinal_str for degrees {degrees}, please provide."
                raise ValueError(msg)
            degrees = DecimalDegrees(degrees, cardinal_str=cardinal_str)

        if not isinstance(degrees, (DecimalDegrees, DegreesMinsSecs)):
            msg = f"unexpected type for degrees. Found: {type(degrees)}, Expected: DecimalDegrees or DegreesMinsSecs"
            raise TypeError(msg)

        if isinstance(degrees, DecimalDegrees):
            self.decimal_degrees = degrees
        else:
            self.degrees = degrees

    @property
    def decimal_degrees(self) -> DecimalDegrees:
        return self._decimal_degrees

    @decimal_degrees.setter
    def decimal_degrees(self, value: DecimalDegrees):
        self._decimal_degrees = value
        self._degrees = value.to_degrees_min_s()

    @property
    def degrees(self) -> DegreesMinsSecs:
        return self._degrees

    @degrees.setter
    def degrees(self, value: DegreesMinsSecs):
        self._degrees = value
        self._decimal_degrees = value.to_decimal_degrees()

    def __repr__(self) -> str:
        return self.degrees.to_str()

    def to_str(self) -> str:
        return self.degrees.to_str()


class Latitude(_LatLonBase):
    def __init__(
        self,
        degrees: DecimalDegrees | DegreesMinsSecs | float,
        cardinal_str: Literal["N", "S"] | None = None,
    ) -> None:

        if cardinal_str not in ("N", "S", None):
            msg = "Latitude cardinal_str must be one of ('N', 'S', None)"
            raise ValueError(msg)

        if cardinal_str is None and isinstance(degrees, (int, float)) and degrees < 0:
            cardinal_str = "N"

        super().__init__(degrees, cardinal_str=cardinal_str)


class Longitude(_LatLonBase):
    def __init__(
        self,
        degrees: DecimalDegrees | DegreesMinsSecs | float,
        cardinal_str: Literal["E", "W"] | None = None,
    ) -> None:

        if cardinal_str not in ("E", "W", None):
            msg = "Longitude cardinal_str must be one of ('E', 'W', None)"
            raise ValueError(msg)

        if cardinal_str is None and isinstance(degrees, (int, float)) and degrees < 0:
            cardinal_str = "E"

        super().__init__(degrees, cardinal_str=cardinal_str)
