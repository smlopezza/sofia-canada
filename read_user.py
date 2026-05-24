"""
Read a user's conversation and state from Firestore.

Usage:
    python read_user.py                    # list all users
    python read_user.py +1416XXXXXXX      # show conversation for that phone
    python read_user.py last               # show the most recently active user
"""

import sys
from dotenv import load_dotenv

load_dotenv()

from app.clients.firestore_client import get_db, get_all_users, load_user, get_active_contact

SEPARATOR = "-" * 60


def list_users():
    users = get_all_users()
    if not users:
        print("No users found.")
        return
    print(f"\n{'Phone':<20} {'Name':<20} {'State':<25} {'Last active'}")
    print(SEPARATOR)
    for u in sorted(users, key=lambda x: x.last_active or "", reverse=True):
        print(f"{u.phone:<20} {(u.name or '—'):<20} {u.current_state:<25} {u.last_active or '—'}")


def show_user(phone: str):
    user = load_user(phone)
    if not user.name and not user.messages:
        print(f"No user found for {phone}")
        return

    print(f"\n{'=' * 60}")
    print(f"USER: {user.name or '(no name)'} — {phone}")
    print(f"Field: {user.field or '—'} | From: {user.country_of_origin or '—'} | City: {user.city or '—'}")
    print(f"State: {user.current_state} | Language: {user.language}")
    print(f"Time in Canada: {user.time_in_canada or '—'} | Last active: {user.last_active or '—'}")
    if user.about_me:
        print(f"\nAbout Me: {user.about_me}")
    print(f"{'=' * 60}")

    if user.conversation_summary:
        print(f"\n📋 CONVERSATION SUMMARY (compressed history):\n{user.conversation_summary}\n")

    contact_id, contact = get_active_contact(phone)
    if contact:
        print(f"\nACTIVE CONTACT: {contact.name} — {contact.role} at {contact.company}")
        print(f"  Scheduled chat: {contact.scheduled_chat_at or '—'}")
        print(f"  Pre-nudge sent: {contact.pre_nudge_sent_at or '—'}")
        print(f"  Post-checkin sent: {contact.post_nudge_sent_at or '—'}")
        print(f"  Thank-you sent: {contact.thank_you_nudge_sent_at or '—'}")
        if contact.depth_signals:
            print(f"  Depth signals: {contact.depth_signals}")
        if contact.post_call_notes:
            print(f"  Post-call notes: {contact.post_call_notes}")

    messages = user.messages or []
    print(f"\nCONVERSATION ({len(messages)} messages):\n")
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        prefix = "👤 " if role == "user" else "🤖 "

        if isinstance(content, str):
            print(f"{prefix} {content}\n")
        elif isinstance(content, list):
            for block in content:
                btype = block.get("type", "")
                if btype == "text":
                    print(f"{prefix} {block['text']}\n")
                elif btype == "tool_use":
                    print(f"  🔧 [{block.get('name')}] {block.get('input', {})}\n")
                elif btype == "tool_result":
                    print(f"  ✅ [tool_result] {str(block.get('content', ''))[:200]}\n")
                else:
                    print(f"  [{btype}] {str(block)[:200]}\n")


def last_active_user():
    users = get_all_users()
    if not users:
        print("No users found.")
        return None
    return max(users, key=lambda u: u.last_active or "")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg is None:
        list_users()
    elif arg == "last":
        user = last_active_user()
        if user:
            show_user(user.phone)
    else:
        show_user(arg)
