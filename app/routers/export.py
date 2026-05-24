import csv
import io
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.clients.firestore_client import (
    delete_contact,
    get_export_token,
    get_user_contacts,
    load_contact,
    load_user,
    mark_export_token_used,
    save_export_token,
    update_contact_fields,
)
from app.models import ExportToken

router = APIRouter()
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

BASE_URL = os.getenv("BASE_URL", "https://sofia-qhgvxxwh5q-nn.a.run.app")


def generate_export_token(phone: str) -> tuple[str, str]:
    """Generate a 24-hour export token. Returns (token_id, full_url)."""
    token_id = str(uuid.uuid4())
    now = datetime.utcnow()
    token = ExportToken(
        phone=phone,
        created_at=now.isoformat(),
        expires_at=(now + timedelta(hours=24)).isoformat(),
    )
    save_export_token(token_id, token)
    link = f"{BASE_URL}/export?token={token_id}"
    return token_id, link


def _validate_token(token_id: str) -> tuple[ExportToken | None, str | None]:
    """Validate token. Returns (token, error_message)."""
    token = get_export_token(token_id)
    if not token:
        return None, "Link not found."
    if datetime.utcnow().isoformat() > token.expires_at:
        return None, "This link has expired. Ask SofIA for a new one."
    return token, None


@router.get("/export", response_class=HTMLResponse)
def export_view(request: Request, token: str):
    token_obj, error = _validate_token(token)
    if error:
        return HTMLResponse(f"<p>{error}</p>", status_code=400)

    user = load_user(token_obj.phone)
    contacts_with_chats = get_user_contacts(token_obj.phone)

    return templates.TemplateResponse("export.html", {
        "request": request,
        "user": user,
        "contacts": contacts_with_chats,
        "token": token,
    })


@router.get("/export/contacts.csv")
def export_contacts_csv(token: str):
    token_obj, error = _validate_token(token)
    if error:
        return HTMLResponse(f"<p>{error}</p>", status_code=400)

    contacts_with_chats = get_user_contacts(token_obj.phone)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Role", "Company", "Connection Context", "First Registered",
                     "Chat Date", "Chat Notes", "Is Mentor"])
    for _, c in contacts_with_chats:
        if c.chats:
            for chat in c.chats:
                writer.writerow([
                    c.name, c.role, c.company, c.connection_context,
                    c.created_at[:10] if c.created_at else "",
                    chat.get("scheduled_at", "")[:10],
                    chat.get("notes") or "",
                    c.is_mentor,
                ])
        else:
            writer.writerow([
                c.name, c.role, c.company, c.connection_context,
                c.created_at[:10] if c.created_at else "",
                "", "", c.is_mentor,
            ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sofia_contacts.csv"}
    )


@router.get("/export/milestones.csv")
def export_milestones_csv(token: str):
    token_obj, error = _validate_token(token)
    if error:
        return HTMLResponse(f"<p>{error}</p>", status_code=400)

    user = load_user(token_obj.phone)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Milestone", "Date", "Note"])
    for m in (user.milestones or []):
        writer.writerow([
            m.get("label", m.get("key", "")),
            m.get("achieved_at", ""),
            m.get("note", "")
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sofia_milestones.csv"}
    )


@router.get("/export/contacts/{contact_id}", response_class=HTMLResponse)
def contact_edit_form(request: Request, contact_id: str, token: str):
    token_obj, error = _validate_token(token)
    if error:
        return HTMLResponse(f"<p>{error}</p>", status_code=400)
    contact = load_contact(token_obj.phone, contact_id)
    if not contact:
        return HTMLResponse("<p>Contact not found.</p>", status_code=404)
    return templates.TemplateResponse("contact_edit.html", {
        "request": request,
        "contact": contact,
        "contact_id": contact_id,
        "token": token,
    })


@router.post("/export/contacts/{contact_id}")
async def contact_edit_save(
    contact_id: str,
    token: str = Form(...),
    name: str = Form(...),
    role: str = Form(""),
    company: str = Form(""),
    linkedin_url: str = Form(""),
    post_call_notes: str = Form(""),
    is_mentor: str = Form("off"),
):
    token_obj, error = _validate_token(token)
    if error:
        return HTMLResponse(f"<p>{error}</p>", status_code=400)
    updates = {
        "name": name.strip(),
        "role": role.strip(),
        "company": company.strip(),
        "linkedin_url": linkedin_url.strip(),
        "post_call_notes": post_call_notes.strip(),
        "is_mentor": is_mentor == "on",
    }
    update_contact_fields(token_obj.phone, contact_id, updates)
    logger.info("Contact %s updated for %s", contact_id, token_obj.phone)
    return RedirectResponse(url=f"/export?token={token}", status_code=303)


@router.post("/export/contacts/{contact_id}/delete")
async def contact_delete(contact_id: str, token: str = Form(...)):
    token_obj, error = _validate_token(token)
    if error:
        return HTMLResponse(f"<p>{error}</p>", status_code=400)
    delete_contact(token_obj.phone, contact_id)
    logger.info("Contact %s deleted for %s", contact_id, token_obj.phone)
    return RedirectResponse(url=f"/export?token={token}", status_code=303)


@router.get("/export/learnings.csv")
def export_learnings_csv(token: str):
    token_obj, error = _validate_token(token)
    if error:
        return HTMLResponse(f"<p>{error}</p>", status_code=400)

    user = load_user(token_obj.phone)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Topic", "Insight", "Confidence", "Date"])
    for l in (user.learnings or []):
        writer.writerow([
            l.get("topic", ""),
            l.get("insight", ""),
            l.get("confidence", "medium"),
            l.get("saved_at", "")
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sofia_learnings.csv"}
    )
