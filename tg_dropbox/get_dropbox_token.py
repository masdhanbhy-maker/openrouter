"""One-time helper: obtain a long-lived Dropbox refresh token."""
import sys

import requests

key = input("Dropbox app key: ").strip()
secret = input("Dropbox app secret: ").strip()
print(f"\nOpen this URL, click Allow, and copy the code:\n"
      f"https://www.dropbox.com/oauth2/authorize?client_id={key}&response_type=code&token_access_type=offline\n")
code = input("Authorization code: ").strip()
r = requests.post("https://api.dropbox.com/oauth2/token",
                  data={"code": code, "grant_type": "authorization_code"}, auth=(key, secret))
if not r.ok:
    sys.exit(r.text)
print("\nDROPBOX_REFRESH_TOKEN=" + r.json()["refresh_token"])
