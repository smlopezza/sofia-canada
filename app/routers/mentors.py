import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.clients.email_client import send_mentor_links_email
from app.clients.firestore_client import (
    deactivate_mentor,
    delete_mentor,
    get_active_mentors,
    get_mentor_by_email,
    get_mentor_by_id,
    get_mentor_by_token,
    optout_mentor,
    reactivate_mentor,
    save_mentor,
    update_mentor,
)

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/mentors", response_class=HTMLResponse)
def mentor_directory(request: Request, lang: str = "en"):
    lang = lang if lang in ("en", "es") else "en"
    try:
        mentors = get_active_mentors()
    except Exception:
        logger.exception("Failed to load mentors")
        mentors = []
    return templates.TemplateResponse("mentors.html", {
        "request": request,
        "lang": lang,
        "mentors": mentors,
    })


@router.get("/mentors/register", response_class=HTMLResponse)
def mentor_register_form(request: Request, lang: str = "en", submitted: bool = False,
                         token: str = "", already_registered: bool = False):
    lang = lang if lang in ("en", "es") else "en"
    return templates.TemplateResponse("mentor_register.html", {
        "request": request,
        "lang": lang,
        "submitted": submitted,
        "token": token,
        "already_registered": already_registered,
    })


@router.post("/mentors/register")
async def mentor_register_submit(
    name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    company: str = Form(""),
    industry: str = Form(...),
    city: str = Form(...),
    country_of_origin: str = Form(""),
    linkedin: str = Form(""),
    calendly: str = Form(""),
    contact_preference: str = Form("linkedin"),
    languages: List[str] = Form(default=[]),
    bio: str = Form(""),
    lang: str = Form("en"),
):
    lang = lang if lang in ("en", "es") else "en"
    token = str(uuid.uuid4())
    mentor_id = str(uuid.uuid4())
    mentor = {
        "name": name.strip(),
        "email": email.strip().lower(),
        "role": role.strip(),
        "company": company.strip(),
        "industry": industry.strip(),
        "city": city.strip(),
        "country_of_origin": country_of_origin.strip(),
        "linkedin": linkedin.strip(),
        "calendly": calendly.strip(),
        "contact_preference": contact_preference,
        "languages": languages,
        "bio": bio.strip()[:1000],
        "active": True,
        "opt_out_token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Prevent duplicate registration
    existing_id, existing = get_mentor_by_email(email.strip().lower())
    if existing_id and existing:
        send_mentor_links_email(
            name=existing.get("name", ""),
            email=existing.get("email", ""),
            token=existing.get("opt_out_token", ""),
            lang=lang,
        )
        return RedirectResponse(
            url=f"/mentors/register?already_registered=true&token={existing.get('opt_out_token', '')}&lang={lang}",
            status_code=303,
        )

    try:
        save_mentor(mentor_id, mentor)
        logger.info("Mentor registered: %s", email)
    except Exception:
        logger.exception("Failed to save mentor %s", email)

    send_mentor_links_email(name=name.strip(), email=email.strip().lower(), token=token, lang=lang)

    return RedirectResponse(
        url=f"/mentors/register?submitted=true&token={token}&lang={lang}",
        status_code=303,
    )


@router.get("/mentors/manage", response_class=HTMLResponse)
def mentor_manage_form(request: Request, lang: str = "en", sent: bool = False):
    lang = lang if lang in ("en", "es") else "en"
    return templates.TemplateResponse("mentor_manage.html", {
        "request": request,
        "lang": lang,
        "sent": sent,
    })


@router.post("/mentors/manage")
async def mentor_manage_submit(email: str = Form(...), lang: str = Form("en")):
    lang = lang if lang in ("en", "es") else "en"
    mentor_id, mentor = get_mentor_by_email(email.strip().lower())
    if mentor_id and mentor:
        send_mentor_links_email(
            name=mentor.get("name", ""),
            email=mentor.get("email", ""),
            token=mentor.get("opt_out_token", ""),
            lang=lang,
        )
        logger.info("Mentor manage email re-sent to %s", email)
    # Always redirect the same way — don't reveal whether email exists
    return RedirectResponse(url=f"/mentors/manage?sent=true&lang={lang}", status_code=303)


@router.get("/mentors/edit", response_class=HTMLResponse)
def mentor_edit_form(
    request: Request,
    token: str = "",
    lang: str = "en",
    updated: bool = False,
    paused: bool = False,
    activated: bool = False,
):
    lang = lang if lang in ("en", "es") else "en"
    if not token:
        return HTMLResponse("<p>Invalid link.</p>", status_code=400)
    mentor_id, mentor = get_mentor_by_token(token)
    if not mentor_id:
        return HTMLResponse("<p>Invalid link.</p>", status_code=404)
    return templates.TemplateResponse("mentor_edit.html", {
        "request": request,
        "lang": lang,
        "mentor": mentor,
        "token": token,
        "updated": updated,
        "paused": paused,
        "activated": activated,
    })


@router.post("/mentors/edit")
async def mentor_edit_submit(
    token: str = Form(...),
    name: str = Form(...),
    role: str = Form(...),
    company: str = Form(""),
    industry: str = Form(...),
    city: str = Form(...),
    country_of_origin: str = Form(""),
    linkedin: str = Form(""),
    calendly: str = Form(""),
    contact_preference: str = Form("linkedin"),
    languages: List[str] = Form(default=[]),
    bio: str = Form(""),
    lang: str = Form("en"),
):
    lang = lang if lang in ("en", "es") else "en"
    mentor_id, _ = get_mentor_by_token(token)
    if not mentor_id:
        return HTMLResponse("<p>Invalid link.</p>", status_code=404)

    updates = {
        "name": name.strip(),
        "role": role.strip(),
        "company": company.strip(),
        "industry": industry.strip(),
        "city": city.strip(),
        "country_of_origin": country_of_origin.strip(),
        "linkedin": linkedin.strip(),
        "calendly": calendly.strip(),
        "contact_preference": contact_preference,
        "languages": languages,
        "bio": bio.strip()[:1000],
    }
    try:
        update_mentor(mentor_id, updates)
        logger.info("Mentor updated: %s", mentor_id)
    except Exception:
        logger.exception("Failed to update mentor %s", mentor_id)

    return RedirectResponse(
        url=f"/mentors/edit?token={token}&lang={lang}&updated=true",
        status_code=303,
    )


@router.get("/mentors/optout", response_class=HTMLResponse)
def mentor_optout(request: Request, token: str = "", lang: str = "en"):
    """Legacy deactivate link — kept for backward compat with existing emails."""
    lang = lang if lang in ("en", "es") else "en"
    if not token:
        return templates.TemplateResponse("mentor_optout.html", {
            "request": request, "lang": lang, "token": "",
            "message_es": "Enlace no válido.", "message_en": "Invalid link.", "deactivated": False,
        })
    mentor_id, mentor = get_mentor_by_token(token)
    if mentor_id and mentor and mentor.get("active"):
        deactivate_mentor(mentor_id)
        deactivated = True
    elif mentor_id:
        deactivated = False  # already paused
    else:
        return templates.TemplateResponse("mentor_optout.html", {
            "request": request, "lang": lang, "token": "",
            "message_es": "Enlace no válido.", "message_en": "Invalid link.", "deactivated": False,
        })
    return templates.TemplateResponse("mentor_optout.html", {
        "request": request,
        "lang": lang,
        "token": token,
        "deactivated": deactivated,
        "message_es": "Tu perfil está pausado — ya no apareces en el directorio.",
        "message_en": "Your profile is paused — you're no longer visible in the directory.",
    })


@router.post("/mentors/deactivate")
async def mentor_deactivate(token: str = Form(...), lang: str = Form("en")):
    lang = lang if lang in ("en", "es") else "en"
    mentor_id, _ = get_mentor_by_token(token)
    if mentor_id:
        deactivate_mentor(mentor_id)
        logger.info("Mentor deactivated: %s", mentor_id)
    return RedirectResponse(
        url=f"/mentors/edit?token={token}&lang={lang}&paused=true",
        status_code=303,
    )


@router.post("/mentors/reactivate")
async def mentor_reactivate(token: str = Form(...), lang: str = Form("en")):
    lang = lang if lang in ("en", "es") else "en"
    mentor_id, _ = get_mentor_by_token(token)
    if mentor_id:
        reactivate_mentor(mentor_id)
        logger.info("Mentor reactivated: %s", mentor_id)
    return RedirectResponse(
        url=f"/mentors/edit?token={token}&lang={lang}&activated=true",
        status_code=303,
    )


@router.get("/mentors/delete", response_class=HTMLResponse)
def mentor_delete_confirm(request: Request, token: str = "", lang: str = "en"):
    lang = lang if lang in ("en", "es") else "en"
    if not token:
        return HTMLResponse("<p>Invalid link.</p>", status_code=400)
    mentor_id, mentor = get_mentor_by_token(token)
    if not mentor_id:
        return HTMLResponse("<p>Invalid link.</p>", status_code=404)
    return templates.TemplateResponse("mentor_delete.html", {
        "request": request,
        "lang": lang,
        "mentor": mentor,
        "token": token,
    })


@router.post("/mentors/delete")
async def mentor_delete_submit(request: Request, token: str = Form(...), lang: str = Form("en")):
    lang = lang if lang in ("en", "es") else "en"
    mentor_id, _ = get_mentor_by_token(token)
    if mentor_id:
        delete_mentor(mentor_id)
        logger.info("Mentor deleted: %s", mentor_id)
    return templates.TemplateResponse("mentor_deleted.html", {
        "request": request,
        "lang": lang,
    })


# Dynamic route last — must come after all fixed /mentors/* paths
@router.get("/mentors/{mentor_id}", response_class=HTMLResponse)
def mentor_public_profile(request: Request, mentor_id: str, lang: str = "en"):
    lang = lang if lang in ("en", "es") else "en"
    mentor = get_mentor_by_id(mentor_id)
    if not mentor or not mentor.get("active"):
        return HTMLResponse(
            "<p style='font-family:sans-serif;padding:2rem'>Profile not found.</p>",
            status_code=404,
        )
    return templates.TemplateResponse("mentor_profile.html", {
        "request": request,
        "lang": lang,
        "mentor": mentor,
    })
