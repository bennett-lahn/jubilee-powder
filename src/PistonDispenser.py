"""Piston dispenser inventory tracking for Jubilee mold top pistons.

Example:
    Track piston count for one dispenser::

        from src.PistonDispenser import PistonDispenser

        dispenser = PistonDispenser(index=0, num_pistons=10)
        dispenser.remove_piston()
        print(dispenser.num_pistons)
"""


class PistonDispenser:
    """Tracks piston count and ready position for one side-mounted dispenser.

    Physical piston retrieval is executed by the motion platform and
    :class:`~src.Manipulator.Manipulator`; this class maintains the software
    inventory count decremented after each successful retrieval.

    Attributes:
        index: Zero-based dispenser index on the machine.
        num_pistons: Remaining piston count in this dispenser.
        ready_pos: Motion platform position name (e.g. ``"dispenser_ready_0"``).

    Note:
        Piston retrieval workflows go through
        :meth:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine.validated_retrieve_piston`.
        Prefer :class:`~src.JubileeManager.JubileeManager` for high-level
        ``move_to_dispenser()`` / ``get_piston_from_dispenser()`` sequences.
    """

    index: int  # index of the dispenser on the side of the Jubilee
    num_pistons: int  # number of pistons in the dispenser
    ready_pos: str  # State machine position name (e.g., "dispenser_ready_0")

    def __init__(self, index: int, num_pistons: int) -> None:
        """Initialize dispenser state.

        Args:
            index: Zero-based dispenser index on the machine.
            num_pistons: Initial piston count loaded in the dispenser.

        Note:
            ``ready_pos`` is set automatically to ``dispenser_ready_{index}``.
        """
        self.index = index
        self.num_pistons = num_pistons
        self.ready_pos = f"dispenser_ready_{index}"  # Set ready_pos based on index

    def remove_piston(self) -> None:
        """Decrement piston count after a piston is dispensed.

        Called by the motion platform after a validated piston retrieval
        completes.

        Raises:
            ValueError: If ``num_pistons`` is already zero.

        Example:
            Check availability before dispensing::

                if dispenser.num_pistons > 0:
                    dispenser.remove_piston()
                else:
                    print("Dispenser empty - needs refilling")
        """
        if self.num_pistons > 0:
            self.num_pistons -= 1
        else:
            raise ValueError("No pistons in dispenser")
