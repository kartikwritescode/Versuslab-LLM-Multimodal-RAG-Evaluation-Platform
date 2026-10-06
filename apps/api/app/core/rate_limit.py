import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """In-memory sliding window rate limiter for single-instance deployments.

    Note: In a multi-instance or horizontally-scaled production deployment,
    a shared distributed store such as Redis (e.g. redis-py with a sliding window
    sorted set) would replace this process-local limiter.
    """

    def __init__(self, requests_per_minute: int, window_seconds: float = 60.0) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._history: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def __call__(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        async with self._lock:
            timestamps = self._history[client_ip]

            # Evict timestamps outside the sliding window
            cutoff = now - self.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.requests_per_minute:
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + self.window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute.",
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)

    def reset(self) -> None:
        """Clears rate limit history (useful for testing)."""
        self._history.clear()


def create_rate_limiter(requests_per_minute: int) -> Callable[[Request], asyncio.Future[None]]:
    """Factory creating a FastAPI dependency enforcing rate limits per endpoint."""
    return InMemoryRateLimiter(requests_per_minute=requests_per_minute)
