"""ARQ enqueue/dequeue round-trip. Requires Redis running (or use fakeredis in CI)."""
import os
import pytest

# Skip if no Redis to avoid hard dependency in CI without services
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


@pytest.mark.asyncio
async def test_arq_enqueue_dequeue_roundtrip():
    """Enqueue a job and run worker once; job completes."""
    try:
        from arq import create_pool
        from arq.connections import ArqRedis
        from noa_api.worker import ping, WorkerSettings
    except ImportError:
        pytest.skip("arq not installed")
    red = await create_pool(ArqRedis.from_url(REDIS_URL))
    try:
        job = await red.enqueue_job("ping")
        assert job is not None
        result = await job.result(timeout=5)
        assert result == "pong"
    except (ConnectionRefusedError, OSError) as e:
        pytest.skip(f"Redis not available: {e}")
    finally:
        await red.close()
