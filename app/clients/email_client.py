import logging
import os
import resend

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")

FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
BASE_URL = os.getenv("BASE_URL", "https://sofia-qhgvxxwh5q-nn.a.run.app")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", " ")

def send_mentor_links_email(name: str, email: str, token: str, lang: str = "en") -> bool:
    edit_url = f"{BASE_URL}/mentors/edit?token={token}&lang={lang}"
    optout_url = f"{BASE_URL}/mentors/optout?token={token}&lang={lang}"

    if lang == "es":
        subject = "SofIA — Tu perfil de mentor"
        body = f"""
<p>Hola {name},</p>

<p>Gracias por registrarte como mentor en SofIA. Tu perfil ya está visible en el directorio.</p>

<p>Guarda estos enlaces — los necesitas para gestionar tu perfil:</p>

<p>
  <strong>✏️ Editar tu perfil:</strong><br>
  <a href="{edit_url}">{edit_url}</a>
</p>

<p>
  <strong>🚪 Salir del directorio:</strong><br>
  <a href="{optout_url}">{optout_url}</a>
</p>

<p>Si perdiste estos enlaces, puedes volver a solicitarlos en:<br>
<a href="{BASE_URL}/mentors/manage">{BASE_URL}/mentors/manage</a></p>

<p>Gracias por apoyar a recién llegados en su transición profesional.<br>
— El equipo de SofIA</p>
"""
    else:
        subject = "SofIA — Your mentor profile"
        body = f"""
<p>Hi {name},</p>

<p>Thank you for registering as a mentor on SofIA. Your profile is now visible in the directory.</p>

<p>Save these links — you'll need them to manage your profile:</p>

<p>
  <strong>✏️ Edit your profile:</strong><br>
  <a href="{edit_url}">{edit_url}</a>
</p>

<p>
  <strong>🚪 Leave the directory:</strong><br>
  <a href="{optout_url}">{optout_url}</a>
</p>

<p>If you lose these links, you can request them again at:<br>
<a href="{BASE_URL}/mentors/manage">{BASE_URL}/mentors/manage</a></p>

<p>Thank you for supporting newcomers in their professional transition.<br>
— The SofIA team</p>
"""

    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [email],
            "subject": subject,
            "html": body,
        })
        logger.info("Mentor links email sent to %s", email)
        return True
    except Exception:
        logger.exception("Failed to send mentor links email to %s", email)
        return False


def send_daily_digest(waitlist_entries: list[dict], new_mentors: list[dict], date_label: str) -> bool:
    def _waitlist_rows(entries):
        if not entries:
            return "<p style='color:#888'>No new sign-ups.</p>"
        rows = ""
        for e in entries:
            linkedin = f" — <a href='{e['linkedin']}'>{e['linkedin']}</a>" if e.get("linkedin") else ""
            story = f"<br><em style='color:#555'>{e['story']}</em>" if e.get("story") else ""
            rows += f"<li><strong>{e.get('name', '?')}</strong> ({e.get('email', '?')}){linkedin}{story}</li>"
        return f"<ul>{rows}</ul>"

    def _mentor_rows(mentors):
        if not mentors:
            return "<p style='color:#888'>No new mentors.</p>"
        rows = ""
        for m in mentors:
            linkedin = f" — <a href='{m['linkedin']}'>{m['linkedin']}</a>" if m.get("linkedin") else ""
            rows += (
                f"<li><strong>{m.get('name', '?')}</strong> — {m.get('role', '')} at {m.get('company', '')} "
                f"({m.get('city', '')}){linkedin}</li>"
            )
        return f"<ul>{rows}</ul>"

    body = f"""
<h2>SofIA Daily Digest — {date_label}</h2>

<h3>Waitlist ({len(waitlist_entries)} new)</h3>
{_waitlist_rows(waitlist_entries)}

<h3>Mentors ({len(new_mentors)} new)</h3>
{_mentor_rows(new_mentors)}
"""

    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [ADMIN_EMAIL],
            "subject": f"SofIA Daily Digest — {date_label}",
            "html": body,
        })
        logger.info("Daily digest sent for %s", date_label)
        return True
    except Exception:
        logger.exception("Failed to send daily digest for %s", date_label)
        return False
