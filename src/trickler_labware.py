"""Weight-based labware types for powder dispensing molds.

Extends ``science_jubilee`` ``Well`` / ``WellSet`` with gram-based tracking and
state-machine position names used by the manipulator and motion platform.

Example:
    Build a mold set from configured ready positions::

        from src.trickler_labware import Mold, MoldSet

        molds = MoldSet(
            wells={
                "0": Mold(name="0", ready_pos="mold_ready_0", max_weight=60.0),
                "1": Mold(name="1", ready_pos="mold_ready_1", max_weight=60.0),
            }
        )
        molds["0"].set_weight(12.5)
        print(molds["0"].well_id)  # "0"
"""

from dataclasses import dataclass

from science_jubilee.labware.Labware import Well, WellSet

# TODO: x,y,z coordinates for mold slots need to be handled properly once their location is decided in hardware


@dataclass
class Mold(Well):
    """Powder mold that tracks weight in grams instead of liquid volume.

    Attributes:
        valid: Whether this slot should be used (e.g. contains a physical mold).
        has_top_piston: Whether a top piston has been placed on the mold.
        current_weight: Current powder weight in grams.
        target_weight: Target fill weight in grams for the active job.
        max_weight: Maximum capacity in grams, or ``None`` if uncapped.
        ready_pos: State-machine position name (e.g. ``"mold_ready_0"``).

    Example:
        ```python
        mold = Mold(name="0", ready_pos="mold_ready_0", max_weight=60.0)
        mold.add_weight(0.5)
        assert mold.well_id == "0"
        ```

    Note:
        :attr:`well_id` is derived from :attr:`ready_pos` for job logging and UI
        selection. It falls back to :attr:`name` when ``ready_pos`` is unset.
    """

    valid: bool = True
    has_top_piston: bool = False
    current_weight: float = 0.0
    target_weight: float = 0.0
    max_weight: float = None
    ready_pos: str = None

    @property
    def well_id(self) -> str:
        """Return the well identifier for UI and job logging.

        Parses ``ready_pos`` by stripping the ``mold_ready_`` prefix (e.g.
        ``"mold_ready_0"`` → ``"0"``). Falls back to ``name`` when
        ``ready_pos`` is unset.

        Returns:
            str: Stable well identifier string.
        """
        if self.ready_pos:
            # Remove 'mold_ready_' prefix if present
            if self.ready_pos.startswith("mold_ready_"):
                return self.ready_pos.replace("mold_ready_", "", 1)
            return self.ready_pos
        # Fallback to name if ready_pos not set
        return self.name

    def add_weight(self, weight: float) -> None:
        """Add powder weight to the mold.

        Args:
            weight: Weight to add in grams.

        Raises:
            ValueError: If the new total would exceed ``max_weight``.
        """
        if self.max_weight is not None:
            if self.current_weight + weight > self.max_weight:
                raise ValueError(
                    f"Adding {weight}g would exceed max weight of {self.max_weight}g"
                )
        self.current_weight += weight

    def remove_weight(self, weight: float) -> None:
        """Remove powder weight from the mold.

        Args:
            weight: Weight to remove in grams.

        Raises:
            ValueError: If the result would be negative.
        """
        if self.current_weight - weight < 0:
            raise ValueError(f"Removing {weight}g would result in negative weight")
        self.current_weight -= weight

    def set_weight(self, weight: float) -> None:
        """Set the current powder weight.

        Args:
            weight: New weight in grams.

        Raises:
            ValueError: If ``weight`` exceeds ``max_weight``.
        """
        if self.max_weight is not None and weight > self.max_weight:
            raise ValueError(
                f"Weight {weight}g exceeds max weight of {self.max_weight}g"
            )
        self.current_weight = weight

    def get_weight(self) -> float:
        """Return the current powder weight.

        Returns:
            float: Current weight in grams.
        """
        return self.current_weight


@dataclass(repr=False)
class MoldSet(WellSet):
    """Collection of :class:`Mold` instances indexed by name or integer slot.

    Supports the same lookup conventions as ``WellSet`` (name key, integer
    index, or slice for a sub-list).

    Example:
        ```python
        slot = mold_set["0"]       # by well name / key
        first = mold_set[0]        # by integer index
        batch = mold_set[0:4]      # slice returns list[Mold]
        ```

    Note:
        Integer indexing falls back to positional order when the key is not
        present in the ``wells`` mapping.
    """

    def __getitem__(self, id_: str | int):
        """Return one or more :class:`Mold` instances by key, index, or slice.

        Args:
            id_: Mold name, integer index, or slice over slot indices.

        Returns:
            Mold | list[Mold]: A single mold or list when ``id_`` is a slice.
        """
        try:
            if isinstance(id_, slice):
                well_list = []
                start = id_.start
                stop = id_.stop
                if id_.step is not None:
                    step = id_.step
                else:
                    step = 1
                for sub_id in range(start, stop, step):
                    well_list.append(self.wells[sub_id])
                return well_list
            else:
                return self.wells[id_]
        except KeyError:
            return list(self.wells.values())[id_]
