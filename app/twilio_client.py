import os
from twilio.rest import Client

_client = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(
            os.getenv("TWILIO_ACCOUNT_SID"),
            os.getenv("TWILIO_AUTH_TOKEN")
        )
    return _client


def send_message(to_phone: str, body: str):
    get_client().messages.create(
        from_=os.getenv("TWILIO_WHATSAPP_NUMBER"),
        to=f"whatsapp:{to_phone}",
        body=body
    )
