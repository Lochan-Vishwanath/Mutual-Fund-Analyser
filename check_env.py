import os
from dotenv import load_dotenv

load_dotenv()

sender = os.getenv("EMAIL_SENDER")
pwd = os.getenv("MF_EMAIL_PASSWORD")
subs = os.getenv("SUBSCRIBERS")

print("--- ENV DIAGNOSTIC ---")
print(f"EMAIL_SENDER: {sender}")
print(f"MF_EMAIL_PASSWORD length: {len(pwd) if pwd else 0}")
print(f"SUBSCRIBERS: {subs}")

if pwd:
    pwd_clean = pwd.replace(" ", "")
    if len(pwd_clean) != 16:
        print("\n[!] WARNING: Gmail App Passwords should be exactly 16 characters (ignoring spaces).")
    if " " in pwd:
        print("[!] TIP: Remove spaces from the password in your .env file just to be safe.")

if not sender or "@" not in sender:
    print("\n[!] WARNING: EMAIL_SENDER looks invalid.")
