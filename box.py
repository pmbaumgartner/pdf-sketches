from dataclasses import dataclass
from functools import cached_property
from itertools import repeat
from operator import mul
from typing import Tuple

# This is a skeleton that should be converted to a Cython class
@dataclass(frozen=True)
class Box:
    """Assumes origin (0, 0) is in bottom-left corner."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __str__(self) -> str:
        return (
            f"Box(x1={self.x1:.3f}, "
            "y1={self.y1:.3f}, "
            "x2={self.x2:.3f}, "
            "y2={self.y2:.3f})"
        )

    @cached_property
    def center(self) -> Tuple[float, float]:
        x_c = (self.x1 + self.x2) / 2
        y_c = (self.y1 + self.y2) / 2
        return x_c, y_c

    def as_tuple(self):
        return (self.x1, self.y1, self.x2, self.y2)

    @cached_property
    def width(self) -> float:
        return self.x2 - self.x1

    @cached_property
    def height(self) -> float:
        return self.y2 - self.y1

    @cached_property
    def size(self) -> Tuple[float, float]:
        return (self.width, self.height)

    def hdist(self, other: "Box") -> float:
        """Distance between right side of this box and left side of other box.

        If boxes are in the same column and text is perfectly justified,
        and `self` is above `other`, this will return -(width)"""
        return other.x1 - self.x2

    def vdist(self, other: "Box") -> float:
        """Distance between bottom of this box and top of other box.

        If boxes are on the same line and `self` is before `other`,
        this will return -(height)."""
        return self.y1 - other.y2

    def dist_between_centers(self, other: "Box") -> float:
        """Distance between the center of this box and the center of other box."""
        cx, cy = self.center
        ocx, ocy = other.center
        return ((cx - ocx) ** 2 + (cy - ocy) ** 2) ** 0.5

    def precedes_x(self, other: "Box", tol: float = 0.0):
        """As defined by Thick Boundary Rectangle Relations (TBRR) in
        'M. Aiello et. al.: Document understanding for a broad class of documents'"""
        return self.x2 < (other.x1 - tol)

    def precedes_y(self, other: "Box", tol: float = 0.0):
        """As defined by Thick Boundary Rectangle Relations (TBRR) in
        'M. Aiello et. al.: Document understanding for a broad class of documents'

        Note: A few *very important* changes happen if we declare a bottom-left origin.
          - The y1 and y2 positions are flipped compared to the original paper,
            so `a` preceeding `b` means `a` appears above b, implying a higher y1-value,
            since y1 is the 'bottom' (equivalent to 'right' in the x-direction) of `a`
            (while y2 is the 'top' of `b`).
          - This also means we add the tolerance to y2 (not subtract it)
          - This also means we flip the sign of the inequality."""
        return self.y1 > (other.y2 + tol)

    def to_xywh(self) -> Tuple[float, float, float, float]:
        """Converts this box to a (x1, y1, width, height) tuple.
        This representation is used in computer vision tasks
        as well as SVG representations.
        Also note that in those representations,
        the origin is upper-left, so a correct y-position might
        need to be calculated by subtracting from the height."""
        return (self.x1, self.y1, self.width, self.height)

    def scale_coords(self, factor: float) -> Tuple[float, float, float, float]:
        """Scale the coordinates of this box by `factor` and return them as a tuple."""
        return tuple(map(mul, self.as_tuple(), repeat(factor)))
