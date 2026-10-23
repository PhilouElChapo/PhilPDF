"""Emplacements distants : la ou l'on ouvre et enregistre des PDF en dehors de ce PC.

Types de comptes (Preferences > Comptes et emplacements) :
  reseau    dossier reseau ou disque (\\\\NAS\\partage, Z:\\, /mnt/nas) : simple chemin
  synology  NAS Synology par son adresse web (File Station) : http(s)://nas:5000, nasdelaye.homedns.org...
  webdav    WebDAV en http ou https (paquet WebDAV Server du Synology, Nextcloud...)
  ftp       FTP en clair ou FTPS (chiffre)
  gdrive / onedrive   en direct par autorisation (identifiants d'application a venir)

Chaque emplacement offre : lister(dossier), telecharger(chemin, fichier_local), envoyer(fichier_local, chemin),
tester(). Les chemins distants s'ecrivent toujours avec des / et commencent par /.
Les mots de passe ne sont jamais dans les parametres : ils vont dans le coffre du systeme (coffre.py).
"""
import base64, ftplib, io, json, os, posixpath, ssl, time, urllib.error, urllib.parse, urllib.request, uuid
import xml.etree.ElementTree as ET
from .langue import _
from . import coffre

TYPES = {
    "reseau": _("Dossier réseau"),
    "synology": _("NAS Synology (adresse web)"),
    "webdav": "WebDAV",
    "ftp": "FTP / FTPS",
    "gdrive": "Google Drive",
    "onedrive": "OneDrive",
}
DELAI = 20


class ErreurDistant(Exception):
    pass


class BesoinCode(ErreurDistant):
    """Le NAS demande le code de verification en deux etapes."""


class _ApiAbsente(ErreurDistant):
    pass


class Element:
    def __init__(self, nom, chemin, dossier, taille=0, date=0):
        self.nom, self.chemin, self.dossier, self.taille, self.date = nom, chemin, dossier, taille, date

    def __repr__(self):
        return f"<{'D' if self.dossier else 'F'} {self.chemin}>"


def _joindre(dossier, nom):
    return posixpath.join(dossier or "/", nom)


def nouveau_compte(genre):
    return {"id": uuid.uuid4().hex[:10], "type": genre, "nom": _(TYPES[genre]), "adresse": "", "port": 0,
            "utilisateur": "", "dossier": "/", "chiffrement": "tls" if genre == "ftp" else "", "certificat_libre": False}


def cle_compte(c):
    """Meme compte sur deux postes = meme type, meme adresse, meme utilisateur (pour la session)."""
    return f"{c.get('type')}|{(c.get('adresse') or '').lower().rstrip('/')}|{(c.get('utilisateur') or '').lower()}"


def libelle(c):
    return f"{c.get('nom') or _(TYPES.get(c.get('type'), ''))}"


# ---------------------------------------------------------------------------------- base
class Emplacement:
    def __init__(self, compte, mot_de_passe=None, code=None):
        self.c = compte
        self.mdp = mot_de_passe if mot_de_passe is not None else coffre.lire(compte["id"])
        self.code = code

    def racine(self):
        return self.c.get("dossier") or "/"

    def tester(self):
        n = len(self.lister(self.racine()))
        return _("Connexion réussie : {n} élément(s) dans {dossier}.", n=n, dossier=self.racine())

    def fermer(self):
        pass


# ---------------------------------------------------------------------------------- dossier reseau
class Reseau(Emplacement):
    """Dossier reseau ou disque monte : chemins locaux, les / sont convertis."""

    def _local(self, chemin):
        base = self.c.get("adresse") or ""
        rel = [p for p in chemin.split("/") if p]
        return os.path.join(base, *rel)

    def racine(self):
        return "/"

    def lister(self, dossier):
        p = self._local(dossier)
        if not os.path.isdir(p):
            raise ErreurDistant(_("Dossier inaccessible : {dossier}", dossier=p))
        out = []
        for nom in sorted(os.listdir(p), key=str.lower):
            q = os.path.join(p, nom)
            try:
                st = os.stat(q)
            except OSError:
                continue
            out.append(Element(nom, _joindre(dossier, nom), os.path.isdir(q), st.st_size, st.st_mtime))
        return out

    def telecharger(self, chemin, local):
        import shutil
        shutil.copy2(self._local(chemin), local)

    def envoyer(self, local, chemin):
        import shutil
        shutil.copy2(local, self._local(chemin))


# ---------------------------------------------------------------------------------- HTTP commun
class _Http(Emplacement):
    def _base(self):
        a = (self.c.get("adresse") or "").strip().rstrip("/")
        if a and "://" not in a:
            a = "http://" + a
        u = urllib.parse.urlsplit(a)
        if self.c.get("port") and not u.port:
            a = urllib.parse.urlunsplit((u.scheme, f"{u.hostname}:{self.c['port']}", u.path, "", ""))
        return a

    def _contexte(self):
        if self.c.get("certificat_libre"):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return None

    def _ouvrir(self, req):
        try:
            return urllib.request.urlopen(req, timeout=DELAI, context=self._contexte())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ErreurDistant(_("Identifiant ou mot de passe refusé ({code}).", code=e.code))
            raise ErreurDistant(_("Le serveur a répondu {code} : {raison}", code=e.code, raison=e.reason))
        except (urllib.error.URLError, OSError) as e:
            raise ErreurDistant(_("Serveur injoignable : {raison}", raison=getattr(e, "reason", e)))


# ---------------------------------------------------------------------------------- WebDAV
class WebDAV(_Http):
    def _url(self, chemin):
        return self._base() + urllib.parse.quote(chemin)

    def _req(self, methode, chemin, donnees=None, entetes=None):
        r = urllib.request.Request(self._url(chemin), data=donnees, method=methode)
        if self.c.get("utilisateur"):
            jeton = base64.b64encode(f"{self.c['utilisateur']}:{self.mdp or ''}".encode()).decode()
            r.add_header("Authorization", "Basic " + jeton)
        for k, v in (entetes or {}).items():
            r.add_header(k, v)
        return self._ouvrir(r)

    def lister(self, dossier):
        if not dossier.endswith("/"):
            dossier += "/"
        corps = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/>'
                 b'<d:getcontentlength/><d:getlastmodified/></d:prop></d:propfind>')
        with self._req("PROPFIND", dossier, corps, {"Depth": "1", "Content-Type": "application/xml"}) as f:
            arbre = ET.fromstring(f.read())
        ns = {"d": "DAV:"}
        base_chemin = urllib.parse.urlsplit(self._base()).path
        out = []
        for rep in arbre.findall("d:response", ns):
            href = urllib.parse.unquote(urllib.parse.urlsplit(rep.findtext("d:href", "", ns)).path)
            if base_chemin and href.startswith(base_chemin):
                href = href[len(base_chemin):] or "/"
            if href.rstrip("/") == dossier.rstrip("/"):
                continue
            est_dossier = rep.find(".//d:resourcetype/d:collection", ns) is not None
            taille = int(rep.findtext(".//d:getcontentlength", "0", ns) or 0)
            out.append(Element(posixpath.basename(href.rstrip("/")), href.rstrip("/") or "/", est_dossier, taille))
        return sorted(out, key=lambda e: (not e.dossier, e.nom.lower()))

    def telecharger(self, chemin, local):
        with self._req("GET", chemin) as f, open(local, "wb") as g:
            g.write(f.read())

    def envoyer(self, local, chemin):
        with open(local, "rb") as f:
            self._req("PUT", chemin, f.read(), {"Content-Type": "application/pdf"}).close()


# ---------------------------------------------------------------------------------- FTP / FTPS
class FTP(Emplacement):
    def _connexion(self):
        hote = (self.c.get("adresse") or "").replace("ftp://", "").replace("ftps://", "").strip("/")
        port = int(self.c.get("port") or 21)
        try:
            if self.c.get("chiffrement") == "tls":
                ctx = ssl.create_default_context()
                if self.c.get("certificat_libre"):
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                f = ftplib.FTP_TLS(context=ctx, timeout=DELAI)
                f.connect(hote, port)
                f.login(self.c.get("utilisateur") or "anonymous", self.mdp or "")
                f.prot_p()
            else:
                f = ftplib.FTP(timeout=DELAI)
                f.connect(hote, port)
                f.login(self.c.get("utilisateur") or "anonymous", self.mdp or "")
            f.encoding = "utf-8"
            return f
        except ftplib.error_perm as e:
            raise ErreurDistant(_("Identifiant ou mot de passe refusé ({code}).", code=str(e)[:3]))
        except (OSError, ftplib.Error) as e:
            raise ErreurDistant(_("Serveur injoignable : {raison}", raison=e))

    def lister(self, dossier):
        f = self._connexion()
        try:
            out = []
            try:
                for nom, faits in f.mlsd(dossier, facts=["type", "size", "modify"]):
                    if nom in (".", "..") or faits.get("type") in ("cdir", "pdir"):
                        continue
                    out.append(Element(nom, _joindre(dossier, nom), faits.get("type") == "dir", int(faits.get("size") or 0)))
            except ftplib.error_perm:
                lignes = []
                f.retrlines(f"LIST {dossier}", lignes.append)
                for l in lignes:
                    p = l.split(None, 8)
                    if len(p) == 9 and p[8] not in (".", ".."):
                        out.append(Element(p[8], _joindre(dossier, p[8]), l.startswith("d"), int(p[4]) if p[4].isdigit() else 0))
            return sorted(out, key=lambda e: (not e.dossier, e.nom.lower()))
        finally:
            f.close()

    def telecharger(self, chemin, local):
        f = self._connexion()
        try:
            with open(local, "wb") as g:
                f.retrbinary(f"RETR {chemin}", g.write)
        finally:
            f.close()

    def envoyer(self, local, chemin):
        f = self._connexion()
        try:
            with open(local, "rb") as g:
                f.storbinary(f"STOR {chemin}", g)
        finally:
            f.close()


# ---------------------------------------------------------------------------------- Synology File Station
class Synology(_Http):
    """API File Station du DSM (DSM 6 et 7). Verification en deux etapes : code demande une fois,
    puis jeton d'appareil garde dans le coffre."""
    sid = None

    def _api(self, params, donnees=None, entetes=None, brut=False, cgi="entry.cgi"):
        if self.sid and "_sid" not in params and params.get("api") != "SYNO.API.Auth":
            params = dict(params, _sid=self.sid)
        url = f"{self._base()}/webapi/{cgi}?" + urllib.parse.urlencode(params)
        r = urllib.request.Request(url, data=donnees)
        for k, v in (entetes or {}).items():
            r.add_header(k, v)
        f = self._ouvrir(r)
        contenu = f.read()
        if brut and not contenu.lstrip().startswith(b'{"'):
            return contenu
        try:
            rep = json.loads(contenu)
        except ValueError:
            if brut:
                return contenu
            raise ErreurDistant(_("Ce n'est pas un NAS Synology (réponse inattendue)."))
        if not rep.get("success"):
            code = (rep.get("error") or {}).get("code")
            if code in (102, 103, 104):
                raise _ApiAbsente(str(code))
            if code in (403, 406):
                raise BesoinCode(_("Le NAS demande le code de vérification en deux étapes."))
            if code in (400, 401, 402):
                raise ErreurDistant(_("Identifiant ou mot de passe refusé ({code}).", code=code))
            if code in (408, 409, 410):
                raise ErreurDistant(_("Fichier ou dossier introuvable sur le NAS ({code}).", code=code))
            raise ErreurDistant(_("Le NAS a refusé la demande (erreur {code}).", code=code))
        return rep.get("data") or {}

    def connecter(self):
        if self.sid:
            return
        p = {"api": "SYNO.API.Auth", "version": "6", "method": "login", "account": self.c.get("utilisateur", ""),
             "passwd": self.mdp or "", "session": "FileStation", "format": "sid"}
        jeton = coffre.lire(self.c["id"] + ".appareil")
        if jeton:
            p["device_id"] = jeton
        if self.code:
            p.update(otp_code=self.code, enable_device_token="yes", device_name="PhilPDF")
        try:
            d = self._api(p, cgi="entry.cgi")
        except _ApiAbsente:                       # DSM ancien : auth.cgi version 3
            d = self._api(dict(p, version="3"), cgi="auth.cgi")
        self.sid = d.get("sid")
        if d.get("did"):
            coffre.enregistrer(self.c["id"] + ".appareil", d["did"])

    def fermer(self):
        if self.sid:
            try:
                self._api({"api": "SYNO.API.Auth", "version": "6", "method": "logout", "session": "FileStation"})
            except ErreurDistant:
                pass
            self.sid = None

    def lister(self, dossier):
        self.connecter()
        if dossier in ("", "/"):
            d = self._api({"api": "SYNO.FileStation.List", "version": "2", "method": "list_share",
                           "additional": '["size","time"]'})
            elems = d.get("shares", [])
        else:
            d = self._api({"api": "SYNO.FileStation.List", "version": "2", "method": "list", "folder_path": dossier,
                           "additional": '["size","time"]'})
            elems = d.get("files", [])
        out = [Element(e["name"], e["path"], bool(e.get("isdir")), (e.get("additional") or {}).get("size", 0))
               for e in elems]
        return sorted(out, key=lambda e: (not e.dossier, e.nom.lower()))

    def telecharger(self, chemin, local):
        self.connecter()
        contenu = self._api({"api": "SYNO.FileStation.Download", "version": "2", "method": "download",
                             "path": chemin, "mode": "download"}, brut=True)
        if isinstance(contenu, dict):
            raise ErreurDistant(_("Téléchargement refusé par le NAS."))
        with open(local, "wb") as g:
            g.write(contenu)

    def envoyer(self, local, chemin):
        self.connecter()
        dossier, nom = posixpath.split(chemin)
        bord = "----PhilPDF" + uuid.uuid4().hex
        champs = {"api": "SYNO.FileStation.Upload", "version": "2", "method": "upload", "path": dossier,
                  "create_parents": "true", "overwrite": "true"}
        corps = io.BytesIO()
        for k, v in champs.items():
            corps.write(f'--{bord}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        corps.write(f'--{bord}\r\nContent-Disposition: form-data; name="file"; filename="{nom}"\r\n'
                    f'Content-Type: application/octet-stream\r\n\r\n'.encode())
        with open(local, "rb") as f:
            corps.write(f.read())
        corps.write(f"\r\n--{bord}--\r\n".encode())
        self._api({"_sid": self.sid}, donnees=corps.getvalue(),
                  entetes={"Content-Type": f"multipart/form-data; boundary={bord}"})


# ---------------------------------------------------------------------------------- Google Drive / OneDrive
class EnAttente(Emplacement):
    def _refus(self, *a):
        raise ErreurDistant(_("{type} en direct arrive bientôt : l'identifiant d'application de PhilPDF n'est pas encore "
                              "enregistré. En attendant, utilisez le dossier de l'application de bureau.",
                              type=_(TYPES[self.c["type"]])))
    lister = telecharger = envoyer = tester = _refus


CLASSES = {"reseau": Reseau, "synology": Synology, "webdav": WebDAV, "ftp": FTP, "gdrive": EnAttente, "onedrive": EnAttente}


def emplacement(compte, mot_de_passe=None, code=None):
    return CLASSES[compte["type"]](compte, mot_de_passe, code)


# ---------------------------------------------------------------------------------- cache local
def cache(dossier_donnees, compte, chemin):
    """Copie locale d'un fichier distant (ouvert dans PhilPDF le temps du travail)."""
    d = os.path.join(dossier_donnees, "distant", compte["id"], *[p for p in posixpath.dirname(chemin).split("/") if p])
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, posixpath.basename(chemin))
