"""In-memory, chunkable UART transport for deterministic host tests."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class FakeUartEndpoint:
    _incoming: deque[bytes] = field(default_factory=deque)
    _peer: "FakeUartEndpoint | None" = None
    connected: bool = True

    def write(self, data: bytes, *, chunk_size: int | None = None) -> int:
        if not self.connected or self._peer is None or not self._peer.connected:
            raise ConnectionError("fake UART disconnected")
        step = chunk_size or len(data) or 1
        for offset in range(0, len(data), step):
            self._peer._incoming.append(bytes(data[offset:offset + step]))
        return len(data)

    def read(self) -> bytes:
        if not self.connected:
            raise ConnectionError("fake UART disconnected")
        return self._incoming.popleft() if self._incoming else b""

    def disconnect(self) -> None:
        self.connected = False
        self._incoming.clear()

    def reconnect(self) -> None:
        self.connected = True


def fake_uart_pair() -> tuple[FakeUartEndpoint, FakeUartEndpoint]:
    left, right = FakeUartEndpoint(), FakeUartEndpoint()
    left._peer = right
    right._peer = left
    return left, right
