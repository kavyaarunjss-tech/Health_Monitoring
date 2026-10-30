"""Create the VAPID key pair for Web Push and add it to .env (only if not there yet). The private key is never printed.

    VAPID_PUBLIC_KEY   = the browser's applicationServerKey (public by design)
    VAPID_PRIVATE_KEY  = signs every push request (secret; .env is git-ignored)
    VAPID_SUBJECT      = mailto:<your Gmail address> (taken from GMAIL_ADDRESS in .env; the push services contact it if something goes wrong)

usage (project root, aqi env):  python backend\\make_vapid_keys.py
Then restart the server. Keep the keys: new keys invalidate every phone's subscription (switch "Alerts on this phone" on again).
"""
import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ENV = Path(__file__).resolve().parents[1] / ".env"


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def main():
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    have = {line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#")}
    add = []
    if "VAPID_PUBLIC_KEY" in have and "VAPID_PRIVATE_KEY" in have:
        print("VAPID keys are already in .env: nothing changed (new keys would cancel every phone's subscription).")
    else:
        key = ec.generate_private_key(ec.SECP256R1())
        private = b64url(key.private_numbers().private_value.to_bytes(32, "big"))
        public = b64url(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        add += [f"VAPID_PUBLIC_KEY={public}", f"VAPID_PRIVATE_KEY={private}"]
        print("Created a new VAPID key pair (public key starts with " + public[:8] + "...; the private key is not shown).")
    if "VAPID_SUBJECT" not in have:
        gmail = next((line.split("=", 1)[1].strip().strip('"') for line in text.splitlines() if line.startswith("GMAIL_ADDRESS=")), "")
        if gmail:
            add.append(f"VAPID_SUBJECT=mailto:{gmail}")
            print("VAPID_SUBJECT set to mailto:<your GMAIL_ADDRESS>.")
        else:
            print("No GMAIL_ADDRESS in .env: add a line VAPID_SUBJECT=mailto:you@example.com yourself.")
    if add:
        with open(ENV, "a", encoding="utf-8") as fh:
            fh.write(("" if text.endswith("\n") or not text else "\n") + "# Web Push (backend/make_vapid_keys.py)\n" + "\n".join(add) + "\n")
        print(f"Added {len(add)} line(s) to .env. Restart the server.")


if __name__ == "__main__":
    main()
