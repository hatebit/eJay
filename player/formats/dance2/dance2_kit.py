"""One sample-kit row from a Dance eJay 2.0 mix catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Dance2Kit:
    """A kit name and the id range it reserves.

    Attributes:
        name: Stored kit name without the ``00 01`` terminator.
        first_id: First catalog id, or zero when the row reserves nothing.
        last_id: Last catalog id, or zero when the row reserves nothing.
    """

    name: str
    first_id: int
    last_id: int
