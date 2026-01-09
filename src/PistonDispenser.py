class PistonDispenser:
    """
    PistonDispenser is a class representing the piston dispensers on the side of the Jubilee.
    It is used to keep track of the number of pistons in each dispenser.
    """
    index : int      # index of the dispenser on the side of the Jubilee
    num_pistons: int # number of pistons in the dispenser
    ready_pos: str   # State machine position name (e.g., "dispenser_ready_0")

    def __init__(self, index, num_pistons):
        self.index = index
        self.num_pistons = num_pistons
        self.ready_pos = f"dispenser_ready_{index}"  # Set ready_pos based on index

    def remove_piston(self):
        if self.num_pistons > 0:
            self.num_pistons -= 1
        else:
            raise ValueError("No pistons in dispenser")
