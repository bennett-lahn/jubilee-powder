"""
Shared pytest fixtures for the jubilee-automation test suite.

Fixture hierarchy
-----------------
``fake_serial_connection``
    A bare ``FakeSerial`` instance, pre-staged with the ACKs that
    ``Scale.connect()`` consumes.  Yields and closes on teardown.

``test_scale``
    A fully-connected ``Scale`` backed by ``fake_serial_connection``.
    Yields and calls ``disconnect()`` on teardown.

Extending this file
-------------------
Add new fixtures here only when they are shared across more than one test
module.  Module-local fixtures belong in a ``conftest.py`` inside the
relevant sub-package (e.g. ``tests/unit/conftest.py``).
"""

import pytest

from tests.fakes.fake_serial import FakeSerial
from src.Scale import Scale

# The ON command is a dual-ACK command (see DUAL_ACK_COMMANDS in Scale.py).
# Scale.connect() calls display_on() which sends ON and waits for two ACK
# sequences before returning.  Pre-stage both so that connect() succeeds
# without any real hardware.
_ACK = b'\x06\r\n'
_CONNECT_ACKS = _ACK + _ACK  # two ACKs consumed by ON during connect()


@pytest.fixture
def fake_serial_connection() -> FakeSerial:
    """
    Provide a fresh, open ``FakeSerial`` for a single test.

    Pre-conditions
    --------------
    * The receive buffer is pre-loaded with the two ACK sequences that
      ``Scale.connect()`` consumes via ``display_on()``.  Tests that
      need additional staged responses should call
      ``fake_serial_connection.stage_response(...)`` *after* receiving
      this fixture — the connect ACKs will already have been consumed by
      the time a test body executes.

    Teardown
    --------
    ``close()`` is called on the ``FakeSerial`` after each test, setting
    ``is_open`` to ``False`` so that any lingering Scale references see a
    closed port.
    """
    conn = FakeSerial()
    conn.stage_response(_CONNECT_ACKS)
    yield conn
    conn.close()


@pytest.fixture
def test_scale(fake_serial_connection: FakeSerial) -> Scale:
    """
    Provide a ``Scale`` instance that is already connected via ``FakeSerial``.

    Pre-conditions
    --------------
    * Delegates to ``fake_serial_connection``, so the two connect ACKs are
      consumed automatically during ``scale.connect()``.
    * After ``yield``, the ``fake_serial_connection.tx_log`` will contain
      exactly the bytes that the Scale sent during connection (the ON
      command) plus whatever the test itself triggered.

    Teardown
    --------
    ``scale.disconnect()`` is called after each test, ensuring the internal
    ``_is_connected`` flag is cleared and the serial reference is dropped.
    """
    scale = Scale(port="FAKE", serial_instance=fake_serial_connection)
    scale.connect()
    yield scale
    scale.disconnect()
