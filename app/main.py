from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routers.webhook import router as webhook_router
from app.routers.jobs import router as jobs_router
from app.routers.profile import router as profile_router
from app.routers.dashboard import router as dashboard_router
from app.routers.landing import router as landing_router
from app.routers.mentors import router as mentors_router

app = FastAPI()

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

app.include_router(webhook_router)
app.include_router(jobs_router)
app.include_router(profile_router)
app.include_router(dashboard_router)
app.include_router(mentors_router)
app.include_router(landing_router)


@app.get("/health")
def health():
    return {"status": "ok"}
