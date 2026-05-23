"""
Multi-week conversation simulation for SofIA — full arc to job landed.

Arc:
  Week 1  Day 1:   Onboarding → Ana contact registered → first chat scheduled
  Week 1  Day 6:   Pre-chat nudge (Ana chat 1)
  Week 1  Day 7:   Post-chat check-in (Ana chat 1) + reflection
  Week 1  Day 8:   Thank-you nudge (Ana chat 1)
  Week 2  Day 9:   Ana wants second meeting → second chat scheduled
  Week 2  Day 11:  Pre-chat nudge (Ana chat 2)
  Week 2  Day 12:  Post-chat check-in (Ana chat 2) + reflection — Ana introduces Carlos
  Week 2  Day 13:  Thank-you nudge (Ana chat 2)
  Week 3  Day 15:  Carlos registered → first chat scheduled
  Week 3  Day 19:  Pre-chat nudge (Carlos)
  Week 3  Day 20:  Post-chat check-in (Carlos) + reflection — Carlos mentions open role
  Week 3  Day 21:  Thank-you nudge (Carlos)
  Week 4  Day 22:  First interview → interview_stage
  Week 4  Day 23:  Interview reflection
  Week 4  Day 24:  Second round → advancing_in_interviews
  Week 4  Day 26:  Final round passed
  Week 4  Day 27:  Job offer received → job_offer_received
  Week 4  Day 28:  User accepts → job_landed 🎉

Usage:
    python test_multiweek.py

Uses real Claude + Firestore. Mocks send_message and datetime for job triggers.
Nudges are now per-chat — all three jobs fire for both Ana chats and Carlos chat.
"""

import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

from fastapi.testclient import TestClient
from app.main import app
from app.webhook import _process
from app.firestore_client import get_active_contact, save_contact, get_db

client = TestClient(app)
SECRET = os.getenv("CLOUD_SCHEDULER_SECRET", "")
PHONE = "+1555MULTIWEEK"
SEP = "-" * 60


# ── Helpers ───────────────────────────────────────────────────────────────────

def cleanup():
    db = get_db()
    user_ref = db.collection("users").document(PHONE)
    for doc in user_ref.collection("contacts").stream():
        doc.reference.delete()
    user_ref.delete()


def chat(text: str, log: list) -> str | None:
    captured = []
    no_limit = {"free": 9999, "contributor": 9999, "org_sponsored": 9999}
    with patch("app.webhook.send_message", side_effect=lambda p, b: captured.append(b)), \
         patch("app.webhook.RATE_LIMITS", no_limit):
        _process(PHONE, text, str(uuid.uuid4()))
    reply = captured[0] if captured else None
    log.append(("USER", text))
    if reply:
        log.append(("SOFIA", reply))
    return reply


def trigger_job(endpoint: str, mock_now: datetime, log: list, label: str, hour: int = None):
    """
    Fire a scheduler job at a simulated time.
    hour overrides local_hour — pre-chat requires 20, thank-you requires 7.
    """
    captured = []
    effective_hour = hour if hour is not None else mock_now.hour

    class FakeDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return mock_now

    with patch("app.jobs.datetime", FakeDatetime), \
         patch("app.jobs.send_message", side_effect=lambda p, b: captured.append(b)), \
         patch("app.jobs.is_sendable", return_value=True), \
         patch("app.jobs.local_hour", return_value=effective_hour):
        client.post(endpoint, headers={"x-scheduler-secret": SECRET})

    fired = len(captured) > 0
    log.append(("JOB_STATUS", f"[{label}] {'fired ✅' if fired else 'did not fire ❌'}"))
    for msg in captured:
        log.append(("JOB", f"[{label}]\n{msg}"))
    return captured


def set_scheduled_chat_at(chat_time_iso: str, expected_name: str):
    """Force scheduled_chat_at on the active contact, verified by name."""
    contact_id, contact = get_active_contact(PHONE)
    if not contact or not contact_id:
        print(f"   ⚠️  No active contact found — expected '{expected_name}'")
        return
    if expected_name.lower() not in contact.name.lower():
        print(f"   ⚠️  Contact mismatch: expected '{expected_name}', got '{contact.name}' — skipping")
        return
    contact.scheduled_chat_at = chat_time_iso
    save_contact(PHONE, contact_id, contact)
    print(f"   [test] {contact.name}: scheduled_chat_at → {chat_time_iso}")


def nudge_triplet(chat_time: datetime, log: list, label: str):
    """Fire the three nudge jobs for a given chat time."""
    trigger_job(
        "/jobs/pre-chat-nudge",
        mock_now=chat_time - timedelta(hours=14),
        log=log,
        label=f"Pre-chat nudge · {label}",
        hour=20,
    )
    trigger_job(
        "/jobs/post-chat-checkin",
        mock_now=chat_time + timedelta(hours=2),
        log=log,
        label=f"Post-chat check-in · {label}",
    )
    trigger_job(
        "/jobs/thank-you-nudge",
        mock_now=chat_time + timedelta(hours=21),
        log=log,
        label=f"Thank-you nudge · {label}",
        hour=7,
    )


def section(title: str):
    print(f"\n{SEP}\n{title}\n{SEP}")


def print_log(log: list):
    for role, text in log:
        if role == "USER":
            print(f"\n👤  {text}")
        elif role == "SOFIA":
            print(f"\n🤖  {text}")
        elif role == "JOB":
            print(f"\n📲  {text}")
        elif role == "JOB_STATUS":
            print(f"\n   {text}")


# ── Simulation ────────────────────────────────────────────────────────────────

def run():
    cleanup()
    log = []
    now = datetime.utcnow()

    # Normalize to T10:00:00 so scheduled_chat_at and job window math align exactly
    base = now.replace(hour=10, minute=0, second=0, microsecond=0)
    ana_chat_1  = base + timedelta(days=6)
    ana_chat_2  = base + timedelta(days=12)
    carlos_chat = base.replace(hour=14) + timedelta(days=20)

    # ── WEEK 1, DAY 1: Onboarding ─────────────────────────────────────
    section("WEEK 1 · DAY 1 — Onboarding")

    chat("Hola", log)
    chat("Me llamo María. Soy data scientist de México.", log)
    chat("Llegué hace 3 meses a Toronto. Estoy buscando trabajo en data science.", log)
    chat("Estoy enviando aplicaciones pero no recibo respuestas.", log)
    chat("No tengo contactos profesionales aquí todavía. No sé cómo empezar.", log)

    # ── WEEK 1, DAY 2: Ana registered, first chat scheduled ───────────
    section("WEEK 1 · DAY 2 — Ana registered, first chat scheduled")

    chat("Encontré a Ana Gómez en LinkedIn — es Data Engineer en TD Bank, también es de México.", log)
    chat(f"Ana aceptó. Quedamos el {ana_chat_1.strftime('%A %B %d')} a las 10am.", log)
    set_scheduled_chat_at(ana_chat_1.strftime("%Y-%m-%dT10:00:00"), expected_name="Ana")

    # ── WEEK 1, DAYS 6-8: Nudge triplet for Ana chat 1 ────────────────
    section("WEEK 1 · DAYS 6-8 — Nudge triplet (Ana chat 1)")

    nudge_triplet(ana_chat_1, log, "Ana chat 1")

    # User reflection after Ana chat 1
    chat("Fue muy bien. Hablamos casi una hora. Me preguntó por mis proyectos y pidió ver mi GitHub.", log)
    chat("Al final ofreció presentarme a alguien de su equipo sin que se lo pidiera.", log)

    # ── WEEK 2, DAY 9: Ana wants second meeting ────────────────────────
    section("WEEK 2 · DAY 9 — Ana wants second meeting")

    chat("Ana me escribió y quiere volver a reunirse. Dice que quiere escuchar cómo me está yendo.", log)
    set_scheduled_chat_at(ana_chat_2.strftime("%Y-%m-%dT10:00:00"), expected_name="Ana")

    # ── WEEK 2, DAYS 11-13: Nudge triplet for Ana chat 2 ──────────────
    section("WEEK 2 · DAYS 11-13 — Nudge triplet (Ana chat 2)")

    nudge_triplet(ana_chat_2, log, "Ana chat 2")

    # User reflection after Ana chat 2
    chat(f"Tuve el segundo café con Ana hoy ({ana_chat_2.strftime('%B %d')}). Fue diferente — más personal.", log)
    chat("Me presentó a Carlos Ruiz, Senior Data Scientist en RBC. Dijo que deberíamos conectar.", log)

    # ── WEEK 3, DAY 15: Carlos registered, chat scheduled ─────────────
    section("WEEK 3 · DAY 15 — Carlos registered, chat scheduled")

    chat("Carlos aceptó el café. Ana nos presentó por LinkedIn.", log)
    chat(f"Quedamos el {carlos_chat.strftime('%A %B %d')} a las 2pm.", log)
    set_scheduled_chat_at(carlos_chat.strftime("%Y-%m-%dT14:00:00"), expected_name="Carlos")

    # ── WEEK 3, DAYS 19-21: Nudge triplet for Carlos ──────────────────
    section("WEEK 3 · DAYS 19-21 — Nudge triplet (Carlos)")

    nudge_triplet(carlos_chat, log, "Carlos")

    # User reflection after Carlos chat
    chat("El café con Carlos fue increíble. Llevamos casi una hora.", log)
    chat("Me dijo que hay una posición abierta en su equipo en RBC y que cree que sería un buen fit. Me pidió el CV.", log)
    chat("Creo que Carlos se está convirtiendo en mi mentor.", log)

    # ── WEEK 4, DAY 22: First interview ───────────────────────────────
    section("WEEK 4 · DAY 22 — First interview")

    chat("Carlos habló con su manager. Me contactaron de RBC para una entrevista.", log)
    chat("La entrevista es mañana con el hiring manager. Estoy muy nerviosa.", log)

    # ── WEEK 4, DAY 23: Post-interview reflection ──────────────────────
    section("WEEK 4 · DAY 23 — First interview reflection")

    chat("Tuve la entrevista. Creo que fue bien.", log)
    chat("Me hicieron preguntas técnicas sobre modelos de clasificación y cómo comunico resultados a stakeholders.", log)
    chat("Me dijeron que me contactarían en los próximos días para una segunda ronda.", log)

    # ── WEEK 4, DAY 24: Second round ──────────────────────────────────
    section("WEEK 4 · DAY 24 — Second round")

    chat("¡Me llamaron! Quieren una segunda entrevista con el equipo técnico.", log)
    chat("La segunda ronda es el viernes. Son dos entrevistas técnicas el mismo día.", log)

    # ── WEEK 4, DAY 26: Second round passed ───────────────────────────
    section("WEEK 4 · DAY 26 — Second round passed")

    chat("Pasé la segunda ronda. Dijeron que el feedback fue muy positivo.", log)
    chat("Carlos me dijo que espere noticias esta semana.", log)

    # ── WEEK 4, DAY 27: Job offer received ────────────────────────────
    section("WEEK 4 · DAY 27 — Job offer received")

    chat("Me llegó un correo de RBC. Me están ofreciendo el puesto de Data Scientist en el equipo de Carlos.", log)
    chat("El salario está dentro de lo que esperaba. Tengo hasta el viernes para responder.", log)

    # ── WEEK 4, DAY 28: Job landed 🎉 ─────────────────────────────────
    section("WEEK 4 · DAY 28 — Job landed 🎉")

    chat("¡Acepté la oferta! Empiezo en tres semanas. No puedo creer que lo logré.", log)

    # ── Full log ──────────────────────────────────────────────────────
    section("FULL CONVERSATION LOG")
    print_log(log)

    section("CHECK FIRESTORE")
    print(f"  users/{PHONE}")
    print("    current_state  = job_landed")
    print("    contact_count  = 2")
    print("    mentor_count   = 1")
    print(f"  users/{PHONE}/contacts")
    print("    Ana:    chats list with 2 entries, each with pre/post/thankyou nudge timestamps")
    print("    Carlos: is_mentor=True, chats list with 1 entry + nudge timestamps")


if __name__ == "__main__":
    run()
