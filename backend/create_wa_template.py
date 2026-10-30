"""Create the AQI alert WhatsApp template (Twilio Content API) and submit it to WhatsApp for approval as a UTILITY template.

ONLY for an UPGRADED (paid) Twilio account with a registered WhatsApp sender: on a trial account the Content API answers
HTTP 401 / error 20003 ("This feature is not available on a Trial account"), and trial senders can only use Twilio's own
pre-approved templates shown on the Console's "Try out WhatsApp" page.

    python backend\\create_wa_template.py            show what would be created (default, nothing is sent to Twilio)
    python backend\\create_wa_template.py --create   create it and request WhatsApp approval; prints the HX... id

After approval (Console > Messaging > Content Template Builder shows "approved"), put the id into .env:
    TWILIO_WA_CONTENT_SID=HX...        TWILIO_WA_CONTENT_LAYOUT=aqi5
Credentials come from .env (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN); the token is never printed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify_twilio as ntw  # noqa: E402

TEMPLATE = {
    "friendly_name": "aqi_alert_v1",
    "language": "en",
    # sample values (WhatsApp reviews them); the real values come from notify_twilio.alert_fields()
    "variables": {"1": "Silk Board, Bengaluru", "2": "AQI 256 (Poor)", "3": "hour ending 2026-04-24 08:00 (+6 h), issued 2026-04-24 02:00",
                  "4": "Likely", "5": "Lung disease: avoid outdoor physical activities and keep your prescribed medicines readily available [4]"},
    "types": {"twilio/text": {"body": ntw.TEMPLATE_BODY}},
}
APPROVAL = {"name": "aqi_alert_v1", "category": "UTILITY"}


def main():
    print("Template body:", ntw.TEMPLATE_BODY)
    print("Content request:", json.dumps(TEMPLATE, ensure_ascii=False, indent=1))
    print("Approval request:", json.dumps(APPROVAL))
    if "--create" not in sys.argv:
        print("\nDry run: nothing was sent to Twilio. Use --create on an upgraded account.")
        return
    import requests
    e = ntw.env()
    auth = (e["TWILIO_ACCOUNT_SID"], e["TWILIO_AUTH_TOKEN"])
    r = requests.post("https://content.twilio.com/v1/Content", json=TEMPLATE, auth=auth, timeout=30)
    if r.status_code >= 300:
        print(f"Twilio refused to create the template: HTTP {r.status_code}: {r.json().get('code')} {r.json().get('message')}")
        return
    sid = r.json()["sid"]
    print("created:", sid)
    a = requests.post(f"https://content.twilio.com/v1/Content/{sid}/ApprovalRequests/whatsapp", json=APPROVAL, auth=auth, timeout=30)
    print("approval request:", a.status_code, (a.json().get("status") or a.json().get("message")))
    print(f"\nWhen WhatsApp has approved it, add to .env:  TWILIO_WA_CONTENT_SID={sid}   TWILIO_WA_CONTENT_LAYOUT=aqi5")


if __name__ == "__main__":
    main()
