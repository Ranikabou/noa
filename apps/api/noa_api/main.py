"""FastAPI application entry. Health and project CRUD; JWT stub."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from noa_api.middleware.auth import JWTAuthMiddleware
from noa_api.routers import assets, build, floorplan, health, inspiration, parse, projects, status, style
from noa_api.storage.s3 import ensure_bucket


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_bucket()
    yield


app = FastAPI(
    title="NOA AI API",
    description="Floorplan-to-3D Architectural Intelligence",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(JWTAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router, prefix="/v1", tags=["health"])
app.include_router(projects.router, prefix="/v1/projects", tags=["projects"])
app.include_router(floorplan.router, prefix="/v1/projects", tags=["floorplan"])
app.include_router(parse.router, prefix="/v1/projects", tags=["parse"])
app.include_router(inspiration.router, prefix="/v1/projects", tags=["inspiration"])
app.include_router(style.router, prefix="/v1/projects", tags=["style"])
app.include_router(build.router, prefix="/v1/projects", tags=["build"])
app.include_router(status.router, prefix="/v1/projects", tags=["status"])
app.include_router(assets.router, prefix="/v1/assets", tags=["assets"])


@app.get("/", include_in_schema=False)
def root():
    """Redirect to interactive API docs."""
    return RedirectResponse(url="/docs", status_code=302)
