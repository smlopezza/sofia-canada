"""
Job endpoint tests for SofIA scheduled messages.

Tests the three time-triggered nudges without needing Cloud Scheduler:
  - Post-chat check-in  (2h after scheduled_chat_at)
  - Thank-you nudge     (next day 7am, only if post-checkin was already sent)
  - Pre-chat nudge      (evening before scheduled chat)

Usage:
    python test_jobs.py                  # all tests
    python test_jobs.py checkin          # post-chat check-in only
    python test_jobs.py thankyou         # thank-you nudge only
    python test_jobs.py prenudge         # pre-chat nudge only
"""

import os
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv()

# Must be set before importing jobs so _verify() works
os.environ["CLOUD_SCHEDULER_SECRET"] = "test-secret"

from app.models import ContactDoc, UserDoc
from app.jobs import post_chat_checkin, thank_you_nudge, pre_chat_nudge

SEPARATOR = "-" * 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(phone: str, name: str = "Valentina", lang: str = "es") -> UserDoc:
    return UserDoc(
        phone=phone,
        name=name,
        field="data science",
        language=lang,
        timezone="America/Toronto",
        current_state="first_chat_completed",
    )


def make_contact(
    hours_ago: float | None = None,
    hours_ahead: float | None = None,
    post_nudge_sent: bool = False,
    pre_nudge_sent: bool = False,
    name: str = "Ana",
    role: str = "HR Director",
    company: str = "a Toronto tech company",
) -> ContactDoc:
    if hours_ago is not None:
        scheduled = (datetime.utcnow() - timedelta(hours=hours_ago)).isoformat()
    elif hours_ahead is not None:
        scheduled = (datetime.utcnow() + timedelta(hours=hours_ahead)).isoformat()
    else:
        scheduled = datetime.utcnow().isoformat()

    return ContactDoc(
        name=name,
        role=role,
        company=company,
        connection_context="Connected through LinkedIn — shared newcomer and data science background",
        scheduled_chat_at=scheduled,
        post_nudge_sent_at=(datetime.utcnow() - timedelta(hours=1)).isoformat() if post_nudge_sent else None,
        pre_nudge_sent_at=(datetime.utcnow() - timedelta(hours=1)).isoformat() if pre_nudge_sent else None,
        thank_you_nudge_sent_at=None,
    )


def run_job(job_fn, contact: ContactDoc, user: UserDoc, local_h: int = 7) -> list[str]:
    """Run a job function with mocked Firestore + Twilio. Returns captured messages."""
    phone = "+1555" + uuid.uuid4().hex[:7]
    captured = []

    with patch("app.jobs.get_all_contacts", return_value=[(phone, "cid_test", contact)]):
        with patch("app.jobs.load_user", return_value=user):
            with patch("app.jobs.save_contact"):
                with patch("app.jobs.send_message", side_effect=lambda _p, msg: captured.append(msg)):
                    with patch("app.jobs.is_sendable", return_value=True):
                        with patch("app.jobs.local_hour", return_value=local_h):
                            job_fn(x_scheduler_secret="test-secret")

    return captured


def print_result(test_name: str, msgs: list[str], expected_sent: bool = True):
    print(f"\n{SEPARATOR}")
    print(f"TEST: {test_name}")
    print(SEPARATOR)
    if msgs:
        print(f"\n📨  Message sent ({len(msgs[0].split())} words):\n")
        print(msgs[0])
        if not expected_sent:
            print("\n❌  UNEXPECTED — message should have been suppressed")
    else:
        if expected_sent:
            print("\n⚠️   No message sent — check timing window or conditions")
        else:
            print("\n✅  Correctly suppressed — no message sent")


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

def test_post_chat_checkin():
    print("\n\n══ POST-CHAT CHECK-IN (2h after meeting) ══")

    # TC01 — Spanish, ~2h after meeting
    msgs = run_job(
        post_chat_checkin,
        make_contact(hours_ago=2),
        make_user("+15550000001", lang="es"),
    )
    print_result("R21-TC01 — Check-in Spanish, 2h after meeting with Ana", msgs)

    # TC02 — English, ~2h after meeting
    msgs = run_job(
        post_chat_checkin,
        make_contact(hours_ago=2),
        make_user("+15550000002", lang="en"),
    )
    print_result("R21-TC02 — Check-in English, 2h after meeting with Ana", msgs)

    # TC03 — Already sent — should NOT resend
    contact_already_sent = make_contact(hours_ago=2)
    contact_already_sent.post_nudge_sent_at = datetime.utcnow().isoformat()
    msgs = run_job(
        post_chat_checkin,
        contact_already_sent,
        make_user("+15550000003"),
    )
    print_result("R21-TC03 — Should NOT resend if post_nudge already sent", msgs, expected_sent=False)


def test_thank_you_nudge():
    print("\n\n══ THANK-YOU NUDGE (next day 7am) ══")

    # TC04 — Spanish, 24h after meeting, post-checkin was sent
    msgs = run_job(
        thank_you_nudge,
        make_contact(hours_ago=24, post_nudge_sent=True),
        make_user("+15550000004", lang="es"),
        local_h=7,
    )
    print_result("R21-TC04 — Thank-you nudge Spanish, post-checkin already sent", msgs)

    # TC05 — English
    msgs = run_job(
        thank_you_nudge,
        make_contact(hours_ago=24, post_nudge_sent=True),
        make_user("+15550000005", lang="en"),
        local_h=7,
    )
    print_result("R21-TC05 — Thank-you nudge English", msgs)

    # TC06 — Gate: should NOT send if post-checkin was never sent
    msgs = run_job(
        thank_you_nudge,
        make_contact(hours_ago=24, post_nudge_sent=False),
        make_user("+15550000006"),
        local_h=7,
    )
    print_result("R21-TC06 — Should NOT send if post-checkin was never sent", msgs, expected_sent=False)

    # TC07 — Gate: should NOT send outside 7am window
    msgs = run_job(
        thank_you_nudge,
        make_contact(hours_ago=24, post_nudge_sent=True),
        make_user("+15550000007"),
        local_h=10,  # 10am — wrong hour
    )
    print_result("R21-TC07 — Should NOT send outside 7am window (10am)", msgs, expected_sent=False)


def test_pre_chat_nudge():
    print("\n\n══ PRE-CHAT NUDGE (evening before meeting) ══")

    # TC08 — Spanish, meeting in 24h
    msgs = run_job(
        pre_chat_nudge,
        make_contact(hours_ahead=24),
        make_user("+15550000008", lang="es"),
        local_h=20,  # 8pm — the pre-nudge send hour
    )
    print_result("R21-TC08 — Pre-chat nudge Spanish, meeting tomorrow", msgs)

    # TC09 — English
    msgs = run_job(
        pre_chat_nudge,
        make_contact(hours_ahead=24),
        make_user("+15550000009", lang="en"),
        local_h=20,
    )
    print_result("R21-TC09 — Pre-chat nudge English, meeting tomorrow", msgs)

    # TC10 — Gate: should NOT resend if pre_nudge already sent
    contact_pre_sent = make_contact(hours_ahead=24, pre_nudge_sent=True)
    msgs = run_job(
        pre_chat_nudge,
        contact_pre_sent,
        make_user("+15550000010"),
        local_h=20,
    )
    print_result("R21-TC10 — Should NOT resend if pre_nudge already sent", msgs, expected_sent=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode == "checkin":
        test_post_chat_checkin()
    elif mode == "thankyou":
        test_thank_you_nudge()
    elif mode == "prenudge":
        test_pre_chat_nudge()
    else:
        test_post_chat_checkin()
        test_thank_you_nudge()
        test_pre_chat_nudge()

    print(f"\n{SEPARATOR}")
    print("Done.")
    print(SEPARATOR)
