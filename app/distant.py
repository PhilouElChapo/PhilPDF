"""Emplacements distants : la ou l'on ouvre et enregistre des PDF en dehors de ce PC.

Types de comptes (Preferences > Comptes et emplacements) :
  reseau    dossier reseau ou disque (\\\\NAS\\partage, Z:\\, /mnt/nas) : simple chemin
  synology  NAS Synology par son adresse web (File Station) : http(s)://nas:5000, monnas.exemple.org...
  webdav    WebDAV en http ou https (paquet WebDAV Server du Synology, Nextcloud...)
  ftp       FTP en clair ou FTPS (chiffre)
  gdrive / onedrive   en direct par autorisation (identifiants d'application a venir)

Chaque emplacement offre : lister(dossier), telecharger(chemin, fichier_local), envoyer(fichier_local, chemin),
tester(). Les chemins distants s'ecrivent toujours avec des / et commencent par /.
Les mots de passe ne sont jamais dans les parametres : ils vont dans le coffre du systeme (coffre.py).
"""
import base64, contextlib, ftplib, io, json, os, posixpath, re, ssl, time, urllib.error, urllib.parse, urllib.request, uuid
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
    "dropbox": "Dropbox",
    "box": "Box",
}
DELAI = 20
NUAGES = ("gdrive", "onedrive", "dropbox", "box")       # Drives « en direct », autorises par OAuth


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
def masquer(texte):
    """Retire mots de passe, codes et jetons d'une ligne du journal."""
    t = re.sub(r"((?:passwd|password|otp_code|_sid|device_id|access_token|refresh_token|client_secret|code_verifier|code)=)[^&\s]+", r"\1****", str(texte))
    t = re.sub(r"(Authorization: \w+ )\S+", r"\1****", t)
    # secrets reconnaissables meme seuls (sans « nom= » devant) : Google, Claude, Gemini, jetons Google
    t = re.sub(r"GOCSPX-[A-Za-z0-9_\-]+", "GOCSPX-****", t)
    t = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "sk-ant-****", t)
    t = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "AIza****", t)
    t = re.sub(r"\b1//[0-9A-Za-z_\-]{20,}", "1//****", t)
    t = re.sub(r"\bya29\.[0-9A-Za-z_\-.]+", "ya29.****", t)
    return re.sub(r'("(?:client_secret|refresh_token|access_token|password|clef_\w+)"\s*:\s*")[^"]+"', r'\1****"', t)


class Emplacement:
    def __init__(self, compte, mot_de_passe=None, code=None):
        self.c = compte
        self.mdp = mot_de_passe if mot_de_passe is not None else coffre.lire(compte["id"])
        self.code = code
        self.journal = []            # echanges avec le serveur (mots de passe masques), montres si erreur

    def log(self, texte):
        self.journal.append(time.strftime("%H:%M:%S ") + masquer(texte))
        self.journal = self.journal[-200:]
        from .journal import ecrire
        ecrire(libelle(self.c) if isinstance(self.c, dict) else "?", texte)

    def texte_journal(self):
        return "\n".join(self.journal) or _("Aucun échange enregistré.")

    def racine(self):
        return self.c.get("dossier") or "/"

    def tester(self):
        n = len(self.lister(self.racine()))
        return _("Connexion réussie : {n} élément(s) dans {dossier}.", n=n, dossier=self.racine())

    def fermer(self):
        pass

    def modifies(self, dossier):
        """{nom: (taille, repere de version, est_dossier)} pour la synchronisation ; {} si le dossier n'existe pas."""
        try:
            elems = self.lister(dossier)
        except ErreurDistant:
            d = dossier.rstrip("/")
            if not d:
                raise
            parent = posixpath.dirname(d) or "/"
            if posixpath.basename(d) not in self.modifies(parent):     # dossier absent (pas une panne) : rien
                return {}
            raise
        return {e.nom: (e.taille, f"{e.date}|{e.taille}", e.dossier) for e in elems}

    def creer_dossiers(self, chemin):
        """Cree les dossiers parents de chemin s'ils manquent (avant un envoi)."""
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
        os.makedirs(os.path.dirname(self._local(chemin)), exist_ok=True)
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
        self.log(f"→ {req.get_method()} {req.full_url}")
        for k, v in req.header_items():
            if k.lower() in ("authorization", "depth", "content-type"):
                self.log(f"   {k}: {v}")
        if req.data:
            self.log(f"   ({len(req.data)} octets envoyés)")
        try:
            r = urllib.request.urlopen(req, timeout=DELAI, context=self._contexte())
            self.log(f"← {r.status} {r.reason}  {r.headers.get('Content-Type', '')}  {r.headers.get('Server', '')}")
            return r
        except urllib.error.HTTPError as e:
            self.dernier_code = e.code
            try:
                corps = e.read(600).decode("utf-8", "replace")
            except Exception:
                corps = ""
            self.log(f"← {e.code} {e.reason}  {e.headers.get('Server', '') if e.headers else ''}")
            if corps:
                self.log("   " + corps.replace("\n", " ")[:400])
            if e.code in (401, 403):
                raise ErreurDistant(_("Identifiant ou mot de passe refusé ({code}).", code=e.code))
            raise ErreurDistant(_("Le serveur a répondu {code} : {raison}", code=e.code, raison=e.reason))
        except (urllib.error.URLError, OSError) as e:
            raison = getattr(e, "reason", e)
            self.log(f"✕ {type(raison).__name__ if not isinstance(raison, str) else 'Erreur'} : {raison}")
            if isinstance(raison, ssl.SSLError) or "CERTIFICATE" in str(raison).upper():
                raise ErreurDistant(_("Certificat du serveur refusé : {raison}. Cochez « Accepter un certificat non vérifié » "
                                      "si votre NAS utilise un certificat auto-signé.", raison=raison))
            raise ErreurDistant(_("Serveur injoignable : {raison}", raison=raison))


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
            brut = f.read()
        self.log("   " + brut[:300].decode("utf-8", "replace").replace("\n", " "))
        try:
            arbre = ET.fromstring(brut)
        except ET.ParseError:
            raise ErreurDistant(_("Ce n'est pas un serveur WebDAV (réponse inattendue). Vérifiez l'adresse et le port "
                                  "(Synology : 5005 en http, 5006 en https)."))
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
            date = rep.findtext(".//d:getlastmodified", "", ns) or ""
            out.append(Element(posixpath.basename(href.rstrip("/")), href.rstrip("/") or "/", est_dossier, taille, date))
        return sorted(out, key=lambda e: (not e.dossier, e.nom.lower()))

    def telecharger(self, chemin, local):
        with self._req("GET", chemin) as f, open(local, "wb") as g:
            g.write(f.read())

    def envoyer(self, local, chemin):
        self.creer_dossiers(chemin)
        with open(local, "rb") as f:
            self._req("PUT", chemin, f.read(), {"Content-Type": "application/pdf"}).close()

    def creer_dossiers(self, chemin):
        parties = [x for x in posixpath.dirname(chemin).split("/") if x]
        for i in range(1, len(parties) + 1):
            d = "/" + "/".join(parties[:i]) + "/"
            if d in getattr(self, "_dossiers_vus", set()):
                continue
            try:
                self._req("MKCOL", d).close()
            except ErreurDistant:
                pass                                   # deja la (405) : normal
            self.__dict__.setdefault("_dossiers_vus", set()).add(d)


# ---------------------------------------------------------------------------------- FTP / FTPS
class FTP(Emplacement):
    """Chaque operation est faite dans _capture : le dialogue FTP complet va dans le journal."""
    @contextlib.contextmanager
    def _capture(self):
        tampon = io.StringIO()
        try:
            with contextlib.redirect_stdout(tampon):
                yield
        finally:
            for l in tampon.getvalue().splitlines():
                self.log(l.replace("*cmd*", "→").replace("*resp*", "←").replace("*put*", "→").replace("*get*", "←"))

    def _connexion(self):
        hote = (self.c.get("adresse") or "").replace("ftp://", "").replace("ftps://", "").strip("/")
        if ":" in hote and not self.c.get("port"):
            hote, p = hote.rsplit(":", 1)
            port = int(p) if p.isdigit() else 21
        else:
            port = int(self.c.get("port") or 21)
        self.log(f"→ connexion {'FTPS' if self.c.get('chiffrement') == 'tls' else 'FTP'} {hote}:{port}")
        try:
            if self.c.get("chiffrement") == "tls":
                ctx = ssl.create_default_context()
                if self.c.get("certificat_libre"):
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                f = ftplib.FTP_TLS(context=ctx, timeout=DELAI)
                f.set_debuglevel(1)
                f.connect(hote, port)
                f.login(self.c.get("utilisateur") or "anonymous", self.mdp or "")
                f.prot_p()
            else:
                f = ftplib.FTP(timeout=DELAI)
                f.set_debuglevel(1)
                f.connect(hote, port)
                f.login(self.c.get("utilisateur") or "anonymous", self.mdp or "")
            f.encoding = "utf-8"
            return f
        except ftplib.error_perm as e:
            self.log(f"← {e}")
            raise ErreurDistant(_("Identifiant ou mot de passe refusé ({code}).", code=str(e)[:3]))
        except (OSError, ftplib.Error) as e:
            self.log(f"✕ {type(e).__name__} : {e}")
            raise ErreurDistant(_("Serveur injoignable : {raison}", raison=e))

    def _lister(self, dossier):
        f = self._connexion()
        try:
            out = []
            try:
                for nom, faits in f.mlsd(dossier, facts=["type", "size", "modify"]):
                    if nom in (".", "..") or faits.get("type") in ("cdir", "pdir"):
                        continue
                    out.append(Element(nom, _joindre(dossier, nom), faits.get("type") == "dir", int(faits.get("size") or 0),
                                       faits.get("modify", "")))
            except ftplib.error_perm:
                lignes = []
                try:
                    f.retrlines(f"LIST {dossier}", lignes.append)
                except ftplib.error_perm:
                    raise ErreurDistant(_("Dossier inaccessible : {dossier}", dossier=dossier))
                for l in lignes:
                    p = l.split(None, 8)
                    if len(p) == 9 and p[8] not in (".", ".."):
                        out.append(Element(p[8], _joindre(dossier, p[8]), l.startswith("d"), int(p[4]) if p[4].isdigit() else 0,
                                           " ".join(p[5:8])))
            return sorted(out, key=lambda e: (not e.dossier, e.nom.lower()))
        finally:
            f.close()

    def _telecharger(self, chemin, local):
        f = self._connexion()
        try:
            with open(local, "wb") as g:
                f.retrbinary(f"RETR {chemin}", g.write)
        finally:
            f.close()

    def _envoyer(self, local, chemin):
        f = self._connexion()
        try:
            parties = [x for x in posixpath.dirname(chemin).split("/") if x]
            for i in range(1, len(parties) + 1):
                try:
                    f.mkd("/" + "/".join(parties[:i]))
                except ftplib.error_perm:
                    pass                               # deja la
            with open(local, "rb") as g:
                f.storbinary(f"STOR {chemin}", g)
        finally:
            f.close()

    def lister(self, dossier):
        with self._capture():
            return self._lister(dossier)

    def telecharger(self, chemin, local):
        with self._capture():
            return self._telecharger(chemin, local)

    def envoyer(self, local, chemin):
        with self._capture():
            return self._envoyer(local, chemin)


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
        self.dernier_code = None
        try:
            f = self._ouvrir(r)
        except ErreurDistant:
            # le DSM repond toujours en JSON : une erreur HTTP veut dire que ce n'est pas le bureau DSM
            if self.dernier_code in (401, 403, 404, 405):
                self._pas_dsm()
            raise
        contenu = f.read()
        self.log("   " + contenu[:300].decode("utf-8", "replace").replace("\n", " "))
        if brut and not contenu.lstrip().startswith(b'{"'):
            return contenu
        try:
            rep = json.loads(contenu)
        except ValueError:
            if brut:
                return contenu
            self._pas_dsm()
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

    def _pas_dsm(self):
        port = urllib.parse.urlsplit(self._base()).port
        if port in (5005, 5006) or self.dernier_code == 401:
            raise ErreurDistant(_("Cette adresse ne répond pas comme le bureau DSM du Synology : c'est sans doute son "
                                  "WebDAV (ports 5005 / 5006). Choisissez le type « WebDAV » pour cette adresse, ou "
                                  "indiquez le port du bureau DSM (5000 en http, 5001 en https)."))
        raise ErreurDistant(_("Ce n'est pas un NAS Synology (réponse inattendue). L'adresse doit être celle du bureau "
                              "DSM (en général port 5000 en http, 5001 en https)."))

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
        out = [Element(e["name"], e["path"], bool(e.get("isdir")), (e.get("additional") or {}).get("size", 0),
                       ((e.get("additional") or {}).get("time") or {}).get("mtime", 0))
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


# ---------------------------------------------------------------------------------- Google Drive (API)
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_ENVOI = "https://www.googleapis.com/upload/drive/v3"
DOSSIER_MIME = "application/vnd.google-apps.folder"


_JETONS = {}        # jetons d'acces gardes en memoire (1 h) : pas de renouvellement a chaque synchronisation


class _DriveOAuth(_Http):
    """Base des Drives autorises par OAuth : jeton d'acces renouvele a partir du jeton durable du coffre."""
    RACINE_ID = None

    def __init__(self, compte, mot_de_passe=None, code=None):
        super().__init__(compte, mot_de_passe, code)
        self.jeton, self.expire, self._ids = None, 0, {"/": self.RACINE_ID}

    def _acces(self):
        from . import oauth
        if self.jeton and time.time() < self.expire:
            return self.jeton
        nom = TYPES[self.c["type"]]
        rt = coffre.lire(self.c["id"] + ".jeton")
        garde = _JETONS.get(self.c["id"])
        if garde and garde[2] == rt and time.time() < garde[1]:
            self.jeton, self.expire = garde[0], garde[1]
            return self.jeton
        if not rt:
            raise ErreurDistant(_("{nom} n'est pas encore autorisé : cliquez sur « Autoriser l'accès » dans le compte.", nom=nom))
        try:
            j = oauth.rafraichir(self.c["type"], rt, self.log)
        except oauth.ErreurAutorisation as e:
            raise ErreurDistant(_("L'autorisation {nom} a expiré ou a été retirée ({raison}) : autorisez à nouveau.",
                                  nom=nom, raison=e))
        if j.get("refresh_token") and j["refresh_token"] != rt:      # Box (et parfois Microsoft) renouvellent le jeton durable
            coffre.enregistrer(self.c["id"] + ".jeton", j["refresh_token"])
        self.jeton, self.expire = j["access_token"], j["expire"]
        _JETONS[self.c["id"]] = (self.jeton, self.expire, coffre.lire(self.c["id"] + ".jeton"))
        return self.jeton

    @staticmethod
    def _cle(chemin):
        return "/" + "/".join(p for p in chemin.split("/") if p)

    def _appel(self, methode, url, donnees=None, entetes=None, brut=False):
        for essai in range(2):
            r = urllib.request.Request(url, data=donnees, method=methode)
            r.add_header("Authorization", "Bearer " + self._acces())
            for k, v in (entetes or {}).items():
                r.add_header(k, v)
            self.dernier_code = None
            try:
                with self._ouvrir(r) as f:
                    contenu = f.read()
                break
            except ErreurDistant:
                if self.dernier_code == 401 and essai == 0:
                    self.jeton = None          # jeton expire : on en redemande un
                    _JETONS.pop(self.c["id"], None)
                    continue
                raise
        if brut:
            return contenu
        return json.loads(contenu or b"{}")

    def _image_publique(self, url):
        """Photo de profil a une adresse publique (sans jeton)."""
        if not url:
            return None
        with self._ouvrir(urllib.request.Request(url)) as f:
            return f.read()

    def photo(self):
        return None


class GoogleDrive(_DriveOAuth):
    """Google Drive en direct (autorisation drive.file : PhilPDF ne voit que les fichiers qu'il a crees ou
    ouverts). Les chemins /Dossier/Fichier.pdf sont resolus par nom a partir de la racine du Drive."""
    RACINE_ID = "root"

    def _q(self, q):
        return f"{DRIVE_API}/files?" + urllib.parse.urlencode({
            "q": q, "fields": "files(id,name,mimeType,size,modifiedTime)", "pageSize": "1000", "spaces": "drive"})

    @staticmethod
    def _echapper(nom):
        return nom.replace("\\", "\\\\").replace("'", "\\'")

    def _id(self, chemin, creer=False):
        """Identifiant du dossier ou fichier ; creer=True cree les dossiers manquants."""
        chemin = "/" + "/".join(p for p in chemin.split("/") if p)
        if chemin in self._ids:
            return self._ids[chemin]
        parent_chemin, nom = posixpath.split(chemin)
        parent = self._id(parent_chemin, creer)
        if parent is None:
            return None
        fichiers = self._appel("GET", self._q(f"name = '{self._echapper(nom)}' and '{parent}' in parents and trashed = false"))
        trouves = fichiers.get("files", [])
        if trouves:
            self._ids[chemin] = trouves[0]["id"]
            return trouves[0]["id"]
        if not creer:
            return None
        d = self._appel("POST", f"{DRIVE_API}/files?fields=id",
                        json.dumps({"name": nom, "mimeType": DOSSIER_MIME, "parents": [parent]}).encode(),
                        {"Content-Type": "application/json"})
        self._ids[chemin] = d["id"]
        return d["id"]

    def lister(self, dossier):
        i = self._id(dossier)
        if i is None:
            raise ErreurDistant(_("Dossier inaccessible : {dossier}", dossier=dossier))
        out = []
        for f in self._appel("GET", self._q(f"'{i}' in parents and trashed = false")).get("files", []):
            est_dossier = f.get("mimeType") == DOSSIER_MIME
            ch = _joindre(dossier, f["name"])
            self._ids["/" + "/".join(p for p in ch.split("/") if p)] = f["id"]
            out.append(Element(f["name"], ch, est_dossier, int(f.get("size") or 0)))
        return sorted(out, key=lambda e: (not e.dossier, e.nom.lower()))

    def telecharger(self, chemin, local):
        i = self._id(chemin)
        if i is None:
            raise ErreurDistant(_("Fichier ou dossier introuvable sur le Drive : {chemin}", chemin=chemin))
        with open(local, "wb") as g:
            g.write(self._appel("GET", f"{DRIVE_API}/files/{i}?alt=media", brut=True))

    def envoyer(self, local, chemin):
        dossier, nom = posixpath.split(chemin)
        parent = self._id(dossier, creer=True)
        with open(local, "rb") as f:
            contenu = f.read()
        type_mime = "application/pdf" if nom.lower().endswith(".pdf") else "application/octet-stream"
        i = self._id(chemin)
        if i:
            self._appel("PATCH", f"{DRIVE_ENVOI}/files/{i}?uploadType=media", contenu, {"Content-Type": type_mime})
            return
        bord = "PhilPDF" + uuid.uuid4().hex
        meta = json.dumps({"name": nom, "parents": [parent]}).encode()
        corps = (f"--{bord}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta +
                 f"\r\n--{bord}\r\nContent-Type: {type_mime}\r\n\r\n".encode() + contenu + f"\r\n--{bord}--".encode())
        d = self._appel("POST", f"{DRIVE_ENVOI}/files?uploadType=multipart&fields=id", corps,
                        {"Content-Type": f"multipart/related; boundary={bord}"})
        self._ids["/" + "/".join(p for p in chemin.split("/") if p)] = d["id"]

    def modifies(self, dossier):
        """{nom: (taille, date ISO)} des fichiers d'un dossier (pour le miroir)."""
        i = self._id(dossier)
        if i is None:
            return {}
        return {f["name"]: (int(f.get("size") or 0), f.get("modifiedTime", ""), f.get("mimeType") == DOSSIER_MIME)
                for f in self._appel("GET", self._q(f"'{i}' in parents and trashed = false")).get("files", [])}

    def qui(self):
        u = self._appel("GET", f"{DRIVE_API}/about?fields=user(emailAddress,displayName)").get("user", {})
        return u.get("emailAddress") or u.get("displayName") or "?"

    def photo(self):
        u = self._appel("GET", f"{DRIVE_API}/about?fields=user(photoLink)").get("user", {})
        return self._image_publique(u.get("photoLink"))

    def tester(self):
        qui = self.qui()
        n = len(self.lister("/"))
        return _("Connexion réussie au Google Drive de {qui} : {n} élément(s) créé(s) ou ouvert(s) par PhilPDF.", qui=qui, n=n)


# ---------------------------------------------------------------------------------- OneDrive (Microsoft Graph)
GRAPH = "https://graph.microsoft.com/v1.0"


class OneDrive(_DriveOAuth):
    def _url(self, chemin, suite=""):
        c = self._cle(chemin)
        if c == "/":
            return f"{GRAPH}/me/drive/root" + (f"/{suite}" if suite else "")
        return f"{GRAPH}/me/drive/root:" + urllib.parse.quote(c) + (f":/{suite}" if suite else "")

    def _enfants(self, dossier):
        url = self._url(dossier, "children") + "?$top=1000&$select=name,size,folder,lastModifiedDateTime"
        out = []
        while url:
            d = self._appel("GET", url)
            out += d.get("value", [])
            url = d.get("@odata.nextLink")
        return out

    def lister(self, dossier):
        return sorted((Element(f["name"], _joindre(dossier, f["name"]), "folder" in f, int(f.get("size") or 0))
                       for f in self._enfants(dossier)), key=lambda e: (not e.dossier, e.nom.lower()))

    def modifies(self, dossier):
        try:
            return {f["name"]: (int(f.get("size") or 0), f.get("lastModifiedDateTime", ""), "folder" in f)
                    for f in self._enfants(dossier)}
        except ErreurDistant:
            if self.dernier_code == 404:
                return {}
            raise

    def telecharger(self, chemin, local):
        with open(local, "wb") as g:
            g.write(self._appel("GET", self._url(chemin, "content"), brut=True))

    def envoyer(self, local, chemin):
        with open(local, "rb") as f:
            contenu = f.read()
        if len(contenu) < 4_000_000:          # envoi simple ; les dossiers manquants sont crees par OneDrive
            self._appel("PUT", self._url(chemin, "content"), contenu, {"Content-Type": "application/octet-stream"})
            return
        s = self._appel("POST", self._url(chemin, "createUploadSession"),
                        json.dumps({"item": {"@microsoft.graph.conflictBehavior": "replace"}}).encode(),
                        {"Content-Type": "application/json"})
        url, pas = s["uploadUrl"], 5 * 327680
        for debut in range(0, len(contenu), pas):
            bout = contenu[debut:debut + pas]
            r = urllib.request.Request(url, data=bout, method="PUT")
            r.add_header("Content-Range", f"bytes {debut}-{debut + len(bout) - 1}/{len(contenu)}")
            self._ouvrir(r).close()

    def qui(self):
        u = self._appel("GET", f"{GRAPH}/me?$select=userPrincipalName,mail,displayName")
        return u.get("mail") or u.get("userPrincipalName") or u.get("displayName") or "?"

    def photo(self):
        return self._appel("GET", f"{GRAPH}/me/photos/96x96/$value", brut=True)

    def tester(self):
        return _("Connexion réussie au OneDrive de {qui} : {n} élément(s) à la racine.", qui=self.qui(), n=len(self.lister("/")))


# ---------------------------------------------------------------------------------- Dropbox
DROPBOX_API = "https://api.dropboxapi.com/2"
DROPBOX_CONTENU = "https://content.dropboxapi.com/2"


class Dropbox(_DriveOAuth):
    def _json(self, url, corps):
        return self._appel("POST", url, json.dumps(corps).encode(), {"Content-Type": "application/json"})

    def _entrees(self, dossier):
        c = self._cle(dossier)
        try:
            d = self._json(f"{DROPBOX_API}/files/list_folder", {"path": "" if c == "/" else c, "limit": 2000})
        except ErreurDistant:
            if self.dernier_code == 409:          # dossier inexistant
                return None
            raise
        out = d.get("entries", [])
        while d.get("has_more"):
            d = self._json(f"{DROPBOX_API}/files/list_folder/continue", {"cursor": d["cursor"]})
            out += d.get("entries", [])
        return out

    def lister(self, dossier):
        e = self._entrees(dossier)
        if e is None:
            raise ErreurDistant(_("Dossier inaccessible : {dossier}", dossier=dossier))
        return sorted((Element(x["name"], _joindre(dossier, x["name"]), x[".tag"] == "folder", int(x.get("size") or 0))
                       for x in e if x[".tag"] in ("file", "folder")), key=lambda e: (not e.dossier, e.nom.lower()))

    def modifies(self, dossier):
        return {x["name"]: (int(x.get("size") or 0), x.get("server_modified", ""), x[".tag"] == "folder")
                for x in (self._entrees(dossier) or []) if x[".tag"] in ("file", "folder")}

    def telecharger(self, chemin, local):
        arg = json.dumps({"path": self._cle(chemin)}, ensure_ascii=True)
        with open(local, "wb") as g:
            g.write(self._appel("POST", f"{DROPBOX_CONTENU}/files/download", b"", {"Dropbox-API-Arg": arg}, brut=True))

    def envoyer(self, local, chemin):
        arg = json.dumps({"path": self._cle(chemin), "mode": "overwrite", "mute": True}, ensure_ascii=True)
        with open(local, "rb") as f:
            self._appel("POST", f"{DROPBOX_CONTENU}/files/upload", f.read(),
                        {"Dropbox-API-Arg": arg, "Content-Type": "application/octet-stream"})

    def qui(self):
        u = self._appel("POST", f"{DROPBOX_API}/users/get_current_account", None)
        return u.get("email") or (u.get("name") or {}).get("display_name") or "?"

    def photo(self):
        u = self._appel("POST", f"{DROPBOX_API}/users/get_current_account", None)
        return self._image_publique(u.get("profile_photo_url"))

    def tester(self):
        return _("Connexion réussie au Dropbox de {qui} : {n} élément(s) à la racine.", qui=self.qui(), n=len(self.lister("/")))


# ---------------------------------------------------------------------------------- Box
BOX_API = "https://api.box.com/2.0"
BOX_ENVOI = "https://upload.box.com/api/2.0"


class Box(_DriveOAuth):
    RACINE_ID = "0"

    def _items(self, ident):
        out, decal = [], 0
        while True:
            d = self._appel("GET", f"{BOX_API}/folders/{ident}/items?fields=name,type,size,modified_at&limit=1000&offset={decal}")
            out += d.get("entries", [])
            decal += len(d.get("entries", []))
            if decal >= int(d.get("total_count", 0)) or not d.get("entries"):
                return out

    def _id(self, chemin, creer=False, type_=None):
        c = self._cle(chemin)
        if c in self._ids:
            return self._ids[c]
        parent_c, nom = posixpath.split(c)
        parent = self._id(parent_c, creer, "folder")
        if parent is None:
            return None
        for x in self._items(parent):
            self._ids[_joindre(parent_c, x["name"])] = x["id"]
            if x["name"] == nom and (type_ is None or x["type"] == type_):
                return x["id"]
        if not creer:
            return None
        d = self._appel("POST", f"{BOX_API}/folders", json.dumps({"name": nom, "parent": {"id": parent}}).encode(),
                        {"Content-Type": "application/json"})
        self._ids[c] = d["id"]
        return d["id"]

    def lister(self, dossier):
        i = self._id(dossier)
        if i is None:
            raise ErreurDistant(_("Dossier inaccessible : {dossier}", dossier=dossier))
        out = []
        for x in self._items(i):
            self._ids[self._cle(_joindre(dossier, x["name"]))] = x["id"]
            out.append(Element(x["name"], _joindre(dossier, x["name"]), x["type"] == "folder", int(x.get("size") or 0)))
        return sorted(out, key=lambda e: (not e.dossier, e.nom.lower()))

    def modifies(self, dossier):
        i = self._id(dossier)
        if i is None:
            return {}
        return {x["name"]: (int(x.get("size") or 0), x.get("modified_at", ""), x["type"] == "folder") for x in self._items(i)}

    def telecharger(self, chemin, local):
        i = self._id(chemin, type_="file")
        if i is None:
            raise ErreurDistant(_("Fichier ou dossier introuvable sur le Drive : {chemin}", chemin=chemin))
        with open(local, "wb") as g:
            g.write(self._appel("GET", f"{BOX_API}/files/{i}/content", brut=True))

    def envoyer(self, local, chemin):
        dossier, nom = posixpath.split(self._cle(chemin))
        parent = self._id(dossier, creer=True, type_="folder")
        existant = self._id(chemin, type_="file")
        with open(local, "rb") as f:
            contenu = f.read()
        bord = "PhilPDF" + uuid.uuid4().hex
        attributs = json.dumps({"name": nom} if existant else {"name": nom, "parent": {"id": parent}}).encode()
        corps = (f'--{bord}\r\nContent-Disposition: form-data; name="attributes"\r\n\r\n'.encode() + attributs +
                 f'\r\n--{bord}\r\nContent-Disposition: form-data; name="file"; filename="{nom}"\r\n'
                 f'Content-Type: application/octet-stream\r\n\r\n'.encode() + contenu + f"\r\n--{bord}--\r\n".encode())
        url = f"{BOX_ENVOI}/files/{existant}/content" if existant else f"{BOX_ENVOI}/files/content"
        d = self._appel("POST", url, corps, {"Content-Type": f"multipart/form-data; boundary={bord}"})
        for x in d.get("entries", []):
            self._ids[self._cle(chemin)] = x["id"]

    def qui(self):
        u = self._appel("GET", f"{BOX_API}/users/me?fields=login,name")
        return u.get("login") or u.get("name") or "?"

    def photo(self):
        return self._appel("GET", f"{BOX_API}/users/me/avatar", brut=True)

    def tester(self):
        return _("Connexion réussie au Box de {qui} : {n} élément(s) à la racine.", qui=self.qui(), n=len(self.lister("/")))


CLASSES = {"reseau": Reseau, "synology": Synology, "webdav": WebDAV, "ftp": FTP, "gdrive": GoogleDrive,
           "onedrive": OneDrive, "dropbox": Dropbox, "box": Box}


def emplacement(compte, mot_de_passe=None, code=None):
    return CLASSES[compte["type"]](compte, mot_de_passe, code)


# ---------------------------------------------------------------------------------- cache local
def cache(dossier_donnees, compte, chemin):
    """Copie locale d'un fichier distant (ouvert dans PhilPDF le temps du travail)."""
    d = os.path.join(dossier_donnees, "distant", compte["id"], *[p for p in posixpath.dirname(chemin).split("/") if p])
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, posixpath.basename(chemin))
