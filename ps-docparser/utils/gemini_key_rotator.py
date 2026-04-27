"""Process-wide Gemini API key rotation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class GeminiKeyLease:
    """Reserved key slot for a single Gemini API request."""

    index: int
    api_key: str
    call_number: int
    max_calls: int
    cycle: int


class GeminiKeyRotator:
    """Rotate Gemini keys after a fixed number of requests per key."""

    def __init__(self, api_keys: list[str] | tuple[str, ...], max_calls_per_key: int = 20):
        cleaned = tuple(key.strip() for key in api_keys if key and key.strip())
        if not cleaned:
            raise ValueError("At least one Gemini API key is required.")

        self._api_keys = cleaned
        self._max_calls = max(1, int(max_calls_per_key))
        self._lock = Lock()
        self._counts = [0] * len(cleaned)
        self._current_index = 0
        self._cycle = 1

    @property
    def key_count(self) -> int:
        return len(self._api_keys)

    @property
    def max_calls_per_key(self) -> int:
        return self._max_calls

    def lease(self) -> GeminiKeyLease:
        """Reserve the next key according to the configured rotation window."""

        with self._lock:
            if all(count >= self._max_calls for count in self._counts):
                self._counts = [0] * len(self._api_keys)
                self._current_index = 0
                self._cycle += 1

            index = self._current_index
            self._counts[index] += 1
            call_number = self._counts[index]

            if call_number >= self._max_calls:
                self._current_index = (index + 1) % len(self._api_keys)

            return GeminiKeyLease(
                index=index,
                api_key=self._api_keys[index],
                call_number=call_number,
                max_calls=self._max_calls,
                cycle=self._cycle,
            )

    def exhaust_key(self, index: int) -> None:
        """Force the given key slot to rotate on the next request."""

        with self._lock:
            if 0 <= index < len(self._counts):
                self._counts[index] = self._max_calls
                if self._current_index == index:
                    self._current_index = (index + 1) % len(self._api_keys)
