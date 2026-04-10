"""
Stateful fake for PySerial's serial.Serial, scoped to the methods and
properties accessed by the Scale driver.

Design notes
------------
* Only the interface actually called by Scale is replicated here.  Do not add
  methods speculatively; expand this class when the Scale class is extended.

* Two-level receive model
  The fake maintains two internal receive structures that map directly to how a
  real serial device behaves:

  1. ``_response_queue`` (deque of bytes) — responses staged by the test,
     waiting to be "sent by the device".  This queue is NOT touched by
     ``reset_input_buffer()`` because the device's pending transmission
     cannot be cancelled from the host side.

  2. ``_rx_buffer`` (bytes) — bytes that have already "arrived" at the host
     and are waiting to be read.  ``reset_input_buffer()`` clears this,
     exactly as PySerial's method does.

  The connection between the two levels is ``write()``: every time the Scale
  sends a command, the fake dequeues the next staged response and moves it
  into ``_rx_buffer``.  This emulates real hardware: send a command, get a
  reply.

* Transmit-side data ("what the Scale sends") is recorded in ``tx_log`` so
  that tests can assert on exact wire bytes without patching anything.
"""

from collections import deque


class FakeSerial:
    """
    In-memory replacement for ``serial.Serial``.

    Assumptions
    -----------
    * Instantiated as "already open" by default (``is_open=True``), mirroring
      what ``serial.Serial`` returns after a successful connection.
    * Thread-safety is intentionally omitted; tests are expected to be
      single-threaded unless explicitly testing concurrent behaviour.
    * One staged response is consumed per ``write()`` call.  If more responses
      than commands are staged, the extras remain in the queue.  If fewer are
      staged, ``write()`` is a no-op on the receive side (simulating a device
      that sends no reply for that command).
    """

    def __init__(self, is_open: bool = True) -> None:
        self._is_open: bool = is_open
        # Pending responses queued by the test; dequeued one-per-write().
        self._response_queue: deque[bytes] = deque()
        # Bytes that have "arrived" and are ready to be read by the Scale.
        self._rx_buffer: bytes = b''
        # Ordered record of every byte-string the Scale has written.
        self._tx_log: list[bytes] = []

    # ------------------------------------------------------------------
    # Properties mirroring serial.Serial
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        """True while the connection has not been closed."""
        return self._is_open

    @property
    def in_waiting(self) -> int:
        """Number of bytes currently available in the receive buffer."""
        return len(self._rx_buffer)

    # ------------------------------------------------------------------
    # Methods mirroring serial.Serial
    # ------------------------------------------------------------------

    def write(self, data: bytes) -> int:
        """
        Record *data* as transmitted by the Scale and deliver the next staged
        response into the live receive buffer.

        Dequeues exactly one entry from ``_response_queue`` (if any) and
        appends it to ``_rx_buffer``, simulating the device's reply arriving
        after a command is sent.  Returns the number of bytes written, as
        PySerial does.
        """
        self._tx_log.append(data)
        if self._response_queue:
            self._rx_buffer += self._response_queue.popleft()
        return len(data)

    def readline(self) -> bytes:
        """
        Return bytes up to and including the first ``\\n`` character.

        Matches PySerial behaviour: if no newline exists in the buffer,
        all remaining bytes are returned and the buffer is cleared.
        """
        if b'\n' in self._rx_buffer:
            idx = self._rx_buffer.index(b'\n')
            line, self._rx_buffer = (
                self._rx_buffer[:idx + 1],
                self._rx_buffer[idx + 1:],
            )
            return line
        data, self._rx_buffer = self._rx_buffer, b''
        return data

    def read(self, size: int = 1) -> bytes:
        """Return up to *size* bytes from the head of the receive buffer."""
        data, self._rx_buffer = self._rx_buffer[:size], self._rx_buffer[size:]
        return data

    def reset_input_buffer(self) -> None:
        """
        Discard all bytes currently in the live receive buffer.

        Does NOT touch ``_response_queue``, matching real PySerial behaviour
        where ``reset_input_buffer()`` only discards bytes already buffered by
        the OS driver, not bytes still in transit from the device.
        """
        self._rx_buffer = b''

    def close(self) -> None:
        """Mark the connection as closed."""
        self._is_open = False

    # ------------------------------------------------------------------
    # Test helpers (not part of the serial.Serial interface)
    # ------------------------------------------------------------------

    def stage_response(self, data: bytes) -> None:
        """
        Queue *data* as the device's response to the next ``write()`` call.

        Multiple calls to ``stage_response()`` build up a FIFO queue.  Each
        subsequent ``write()`` consumes one entry.  Stage responses in the
        same order as the commands that will be sent.

        Example — stage a stable-weight reply for a ``Q`` command::

            fake.stage_response(b'ST,+00100.00  g\\r\\n')
        """
        self._response_queue.append(data)

    @property
    def tx_log(self) -> list[bytes]:
        """
        Ordered list of byte-strings written by the Scale under test.

        Use this in assertions to verify the exact command bytes transmitted::

            assert fake.tx_log[-1] == b'T\\r\\n'
        """
        return self._tx_log
