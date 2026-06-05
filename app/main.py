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

# Create the FastAPI application instance.
app = FastAPI()

# Serve static files from the `static` folder under the `/static` path.
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

# Register routers for the application’s endpoint groups.
app.include_router(webhook_router)  # webhook endpoints for incoming external events
app.include_router(jobs_router)    # job listings and job-related interactions
app.include_router(profile_router) # user profile and profile management pages
app.include_router(dashboard_router) # dashboard views for user/mentor activity
app.include_router(mentors_router) # mentor registration and mentor-facing pages
app.include_router(landing_router) # public landing and informational pages


@app.get("/health")
def health():
    """Health check endpoint used to verify the service is running."""
    return {"status": "ok"}
