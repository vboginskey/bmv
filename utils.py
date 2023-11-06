import asyncio

class SharedCounter:
    """
    Simple shared counter that fires an event once the specified threshold is reached
    """
    def __init__(self, threshold: int) -> None:
        self.count = 0
        self.event = asyncio.Event()
        self.threshold = threshold

    def increment(self) -> None:
        self.count += 1
        if self.count == self.threshold:
            self.event.set()
        