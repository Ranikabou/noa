"""ARQ worker: typed job payloads, enqueue from API. Run with: arq noa_api.worker.WorkerSettings."""
import os
import logging
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from noa_api.jobs.pdf_rasterize import pdf_rasterize
from noa_api.jobs.floorplan_parse import floorplan_parse
from noa_api.jobs.style_inference import style_inference
from noa_api.jobs.geometry_rules import geometry_rules
from noa_api.jobs.model_reconstruct import model_reconstruct

logger = logging.getLogger("noa.worker")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


# Typed job payloads (contract IDs only; max payload 1MB)
class JobPayload:
    """All job kinds reference contracts by ID only."""
    job_type: str
    project_id: str | None = None
    input_contract_id: str | None = None


async def ping(ctx: dict) -> str:
    """Health check job."""
    return "pong"


async def startup(ctx: dict) -> None:
    logger.info("NOA worker started")


async def shutdown(ctx: dict) -> None:
    logger.info("NOA worker shutdown")


class WorkerSettings:
    functions = [ping, pdf_rasterize, floorplan_parse, style_inference, geometry_rules, model_reconstruct]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = 10
    job_timeout = 300


_redis_settings = RedisSettings.from_dsn(REDIS_URL)


async def _get_pool(redis: ArqRedis | None = None) -> ArqRedis:
    return redis or await create_pool(_redis_settings)


async def enqueue_ping(redis: ArqRedis | None = None) -> str | None:
    red = await _get_pool(redis)
    job = await red.enqueue_job("ping")
    return job.job_id if job else None


async def enqueue_pdf_rasterize(asset_id: str, redis: ArqRedis | None = None) -> str | None:
    red = await _get_pool(redis)
    job = await red.enqueue_job("pdf_rasterize", asset_id)
    return job.job_id if job else None


async def enqueue_floorplan_parse(asset_id: str, redis: ArqRedis | None = None) -> str | None:
    red = await _get_pool(redis)
    job = await red.enqueue_job("floorplan_parse", asset_id)
    return job.job_id if job else None


async def enqueue_style_inference(board_id: str, project_id: str, redis: ArqRedis | None = None) -> str | None:
    red = await _get_pool(redis)
    job = await red.enqueue_job("style_inference", board_id, project_id)
    return job.job_id if job else None


async def enqueue_geometry_rules(style_profile_id: str, project_id: str, redis: ArqRedis | None = None) -> str | None:
    red = await _get_pool(redis)
    job = await red.enqueue_job("geometry_rules", style_profile_id, project_id)
    return job.job_id if job else None


async def enqueue_model_reconstruct(project_id: str, redis: ArqRedis | None = None) -> str | None:
    red = await _get_pool(redis)
    job = await red.enqueue_job("model_reconstruct", project_id)
    return job.job_id if job else None
