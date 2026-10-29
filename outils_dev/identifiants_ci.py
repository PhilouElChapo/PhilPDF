"""Fabrication GitHub (Linux) : ecrit app/identifiants.py a partir des secrets du depot (jamais dans le code public)."""
import os

ids = {}
for cle, env in (("gdrive", "GOOGLE"), ("onedrive", "ONEDRIVE"), ("dropbox", "DROPBOX"), ("box", "BOX")):
    i = "".join(os.environ.get(env + "_CLIENT_ID", "").split())
    s = "".join(os.environ.get(env + "_CLIENT_SECRET", "").split())
    if i:
        ids[cle] = {"id": i, "secret": s or None}
    print(cle, ":", "identifiant present" if i else "absent")
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "identifiants.py"), "w") as f:
    f.write("IDENTIFIANTS = " + repr(ids) + "\n")
