import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.clients.firestore_client import get_active_mentors, get_waitlist_by_email, save_waitlist_entry

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
def index(request: Request, lang: str = "en", submitted: bool = False, already_waitlisted: bool = False):
    lang = lang if lang in ("en", "es") else "en"
    try:
        mentors = get_active_mentors()[:3]
    except Exception:
        mentors = []
    return templates.TemplateResponse("index.html", {
        "request": request,
        "lang": lang,
        "submitted": submitted,
        "already_waitlisted": already_waitlisted,
        "mentors": mentors,
    })


@router.post("/waitlist")
async def join_waitlist(
    name: str = Form(...),
    email: str = Form(...),
    linkedin: str = Form(""),
    story: str = Form(""),
    lang: str = Form("en"),
):
    lang = lang if lang in ("en", "es") else "en"
    entry = {
        "name": name.strip(),
        "email": email.strip().lower(),
        "linkedin": linkedin.strip(),
        "story": story.strip(),
        "lang": lang,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if get_waitlist_by_email(email.strip().lower()):
            return RedirectResponse(url=f"/?already_waitlisted=true&lang={lang}", status_code=303)
        save_waitlist_entry(entry)
        logger.info("Waitlist entry saved: %s", email)
    except Exception:
        logger.exception("Failed to save waitlist entry for %s", email)

    return RedirectResponse(url=f"/?submitted=true&lang={lang}", status_code=303)


@router.get("/guide", response_class=HTMLResponse)
def guide(request: Request, lang: str = "en"):
    lang = lang if lang in ("en", "es") else "en"
    return templates.TemplateResponse("guide.html", {"request": request, "lang": lang})


@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request, lang: str = "en"):
    lang = lang if lang in ("en", "es") else "en"
    return templates.TemplateResponse("privacy.html", {"request": request, "lang": lang})
