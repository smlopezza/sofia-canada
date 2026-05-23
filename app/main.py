from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.webhook import router as webhook_router
from app.jobs import router as jobs_router
from app.export import router as export_router

app = FastAPI()

app.include_router(webhook_router)
app.include_router(jobs_router)
app.include_router(export_router)


@app.get("/health")
def health():
    return {"status": "ok"}
