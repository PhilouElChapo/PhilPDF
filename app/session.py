"""Session partagee entre machines (doctrine validee le 22/10/2026).

Le Drive ne sert que de BOITE AUX LETTRES : il contient <Drive>/PhilPDF/session.json, la liste
des fichiers ouverts sur chaque machine. Les PDF eux-memes ne sont jamais copies.

Chaque machine a un ALIAS ("Pharmacie", "Maison"...) et declare ses RACINES (dossiers ou sont
ses documents : C:\\Users\\Phil, D:\\Documents, le NAS...). Pour chaque fichier, la session note :
chemin d'origine, chemin relatif au dossier utilisateur, racine d'origine et chemin relatif a
elle, nom, taille, empreinte, page affichee, machine et date.

Reprise sur une autre machine, en cascade :
  0. correspondance de dossiers deja apprise entre ces deux machines ;
  1. le chemin exact ;
  2. le meme chemin transpose sur le dossier utilisateur de cette machine ;
  3. le meme chemin relatif sous chacune des racines declarees ici ;
  4. recherche par nom dans les racines, confirmee par l'empreinte ;
  5. recherche par empreinte (fichier renomme), plus longue, en arriere-plan ;
  6. sinon : "introuvable sur <alias> (ouvert sur <machine> le <date>)".
Toute correspondance trouvee est APPRISE (dossier source -> dossier ici) et partagee via le Drive :
la fois suivante, c'est immediat.
"""
import datetime, hashlib, json, os, subprocess, sys, time
from .langue import _

LIMITE_FICHIERS = 30_000           # recherche rapide et silencieuse : quelques secondes au plus
DELAI_SILENCIEUX = 8               # secondes, verification au demarrage
IGNORES = {"AppData", "node_modules", "Windows", "Program Files", "Program Files (x86)", "ProgramData",
           "__pycache__", "System Volume Information", "Library", "snap"}
CONNUS = (("documents", _('Documents')), ("telechargements", _('Téléchargements')), ("bureau", _('Bureau')),
          ("nas", "NAS"), ("maison", _('Dossier utilisateur')))


def _dossier_windows(guid):
    """Dossier connu de Windows (suit les deplacements : Documents sur D:, sur OneDrive...)."""
    import ctypes
    from ctypes import wintypes
    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
    g = guid.strip("{}").split("-")
    v = GUID(int(g[0], 16), int(g[1], 16), int(g[2], 16),
             (ctypes.c_ubyte * 8)(*bytes.fromhex(g[3] + g[4])))
    p = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(v), 0, None, ctypes.byref(p)) != 0:
        return None
    r = p.value
    ctypes.windll.ole32.CoTaskMemFree(p)
    return r


def _dossier_linux(nom, defauts):
    """Dossier XDG (~/Documents, ~/Téléchargements...) : equivalent Linux des dossiers Windows."""
    try:
        r = subprocess.run(["xdg-user-dir", nom], capture_output=True, text=True, timeout=2).stdout.strip()
        if r and r != os.path.expanduser("~"):
            return r
    except (OSError, subprocess.SubprocessError):
        pass
    for d in defauts:
        p = os.path.join(os.path.expanduser("~"), d)
        if os.path.isdir(p):
            return p
    return None


_cache_connus = {}


def dossiers_connus(params=None):
    """{clef: chemin} des dossiers par defaut de CETTE machine. Les memes clefs designent l'equivalent
    sur chaque machine et chaque systeme : %USERPROFILE%\\Documents sous Windows = ~/Documents sous Linux."""
    if not _cache_connus:
        maison = os.path.expanduser("~")
        if sys.platform == "win32":
            for clef, guid in (("documents", "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"),
                               ("telechargements", "{374DE290-123F-4565-9164-39C4925E467B}"),
                               ("bureau", "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}")):
                try:
                    _cache_connus[clef] = _dossier_windows(guid)
                except Exception:
                    _cache_connus[clef] = None
        else:
            _cache_connus["documents"] = _dossier_linux("DOCUMENTS", ["Documents"])
            _cache_connus["telechargements"] = _dossier_linux("DOWNLOAD", ["Téléchargements", "Downloads"])
            _cache_connus["bureau"] = _dossier_linux("DESKTOP", ["Bureau", "Desktop"])
        _cache_connus["maison"] = maison
    d = {k: v for k, v in _cache_connus.items() if v and os.path.isdir(v)}
    if params is not None and params.get("nas") and os.path.isdir(params["nas"]):
        d["nas"] = params["nas"]
    return d


def empreinte(chemin):
    """Empreinte rapide : taille + debut + fin du fichier (suffit a reconnaitre un PDF)."""
    try:
        t = os.path.getsize(chemin)
        h = hashlib.sha1(str(t).encode())
        with open(chemin, "rb") as f:
            h.update(f.read(65536))
            if t > 131072:
                f.seek(-65536, 2)
                h.update(f.read(65536))
        return h.hexdigest()
    except OSError:
        return None


def _norm(p):
    return os.path.normcase(os.path.normpath(p))


def _relatif(chemin, base):
    try:
        if base and _norm(chemin).startswith(_norm(base) + os.sep):
            return os.path.relpath(chemin, base)
    except ValueError:
        pass
    return None


def _decouper(rel):
    """Chemin relatif ecrit sous Windows ou Linux -> liste de morceaux."""
    return [x for x in rel.replace("\\", "/").split("/") if x]


class Session:
    def __init__(self, params, chemin_session, chemin_corresp):
        self.params = params
        self.chemin = chemin_session
        self.chemin_corresp = chemin_corresp

    # ------------------------------------------------------------ ou chercher sur cette machine
    def racines(self):
        """Dossiers par defaut (Documents, Telechargements, Bureau, NAS, dossier utilisateur) puis ceux
        ajoutes en mode avance ; les plus precis d'abord, sans doublon."""
        r = []
        for x in [v for k, v in dossiers_connus(self.params).items() if k != "maison"] + \
                 [x for x in self.params.get("racines", []) if x and os.path.isdir(x)] + [os.path.expanduser("~")]:
            if not any(_norm(x) == _norm(y) for y in r):
                r.append(x)
        return r

    # ------------------------------------------------------------ lecture / ecriture
    def lire(self):
        try:
            with open(self.chemin, encoding="utf-8") as f:
                d = json.load(f)
            # ancienne forme 0.1 : {machine: [chemins]}
            return {m: (v if isinstance(v, dict) else {"maj": "", "fichiers": [{"chemin": c, "nom": os.path.basename(c)} for c in v]})
                    for m, v in d.items()}
        except (OSError, ValueError):
            return {}

    def ma_date(self):
        return self.lire().get(self.params["machine"], {}).get("maj", "")

    def ecrire(self, ouverts):
        """ouverts = [(chemin, page, zoom)] des documents ouverts ici."""
        maison = os.path.expanduser("~")
        connus = dossiers_connus(self.params)
        fichiers = []
        for chemin, page, zoom in ouverts:
            if not chemin or not os.path.exists(chemin):
                continue
            e = {"chemin": chemin, "nom": os.path.basename(chemin), "taille": os.path.getsize(chemin),
                 "empreinte": empreinte(chemin), "page": page, "zoom": zoom,
                 "relatif_maison": _relatif(chemin, maison)}
            # dossier par defaut le plus precis qui le contient (Documents plutot que dossier utilisateur)
            for clef, base in sorted(connus.items(), key=lambda kv: -len(kv[1])):
                rel = _relatif(chemin, base)
                if rel:
                    e["connu"], e["relatif_connu"] = clef, rel
                    break
            for r in self.params.get("racines", []):
                rel = _relatif(chemin, r)
                if rel:
                    e["racine"], e["relatif_racine"] = r, rel
                    break
            fichiers.append(e)
        d = self.lire()
        d[self.params["machine"]] = {"maj": datetime.datetime.now().isoformat(timespec="minutes"),
                                     "maison": maison, "systeme": sys.platform, "fichiers": fichiers}
        try:
            with open(self.chemin, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def autres_machines(self):
        """[(machine, date, nb_fichiers)] des autres machines, la plus recente d'abord."""
        out = [(m, v.get("maj", ""), len(v.get("fichiers", []))) for m, v in self.lire().items()
               if m != self.params["machine"] and v.get("fichiers")]
        return sorted(out, key=lambda x: x[1], reverse=True)

    def discordance(self, ouverts=()):
        """Autre machine dont la session est plus recente que la notre ET differente de ce qui est ouvert
        ici. Renvoie (machine, date, fichiers) ou None."""
        autres = self.autres_machines()
        if not autres:
            return None
        m, date, _x = autres[0]
        if date <= self.ma_date():
            return None
        fichiers = self.lire()[m]["fichiers"]
        ici = {empreinte(c) for c in ouverts if c}
        if fichiers and all(e.get("empreinte") in ici for e in fichiers):
            return None
        return m, date, fichiers

    # ------------------------------------------------------------ correspondances apprises
    def _corresp(self):
        try:
            with open(self.chemin_corresp, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _ecrire_corresp(self, c):
        try:
            with open(self.chemin_corresp, "w", encoding="utf-8") as f:
                json.dump(c, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def apprendre(self, machine, dossier_source, dossier_ici):
        c = self._corresp()
        c.setdefault(f"{machine} -> {self.params['machine']}", {})[dossier_source.replace("\\", "/")] = dossier_ici
        self._ecrire_corresp(c)

    def correspondances(self):
        """[(machine_source, dossier_source, dossier_ici)] apprises pour cette machine."""
        out = []
        for cle, d in self._corresp().items():
            src, _x, ici = cle.partition(" -> ")
            if ici == self.params["machine"]:
                out += [(src, a, b) for a, b in d.items()]
        return sorted(out)

    def oublier(self, machine, dossier_source):
        c = self._corresp()
        c.get(f"{machine} -> {self.params['machine']}", {}).pop(dossier_source, None)
        self._ecrire_corresp(c)

    # ------------------------------------------------------------ recherche
    def _confirme(self, chemin, e):
        if not os.path.isfile(chemin):
            return False
        if e.get("taille") is not None and os.path.getsize(chemin) != e["taille"]:
            return False
        return not e.get("empreinte") or empreinte(chemin) == e["empreinte"]

    def retrouver_direct(self, machine, e):
        """Etapes sans parcours de disque (instantanees). Renvoie (chemin, comment) ou (None, None)."""
        src = e["chemin"].replace("\\", "/")
        # 1. correspondance apprise (le dossier lui-meme ou un dossier parent)
        appris = self._corresp().get(f"{machine} -> {self.params['machine']}", {})
        for d_src, d_ici in sorted(appris.items(), key=lambda x: -len(x[0])):
            if src.lower().startswith(d_src.lower().rstrip("/") + "/"):
                cand = os.path.join(d_ici, *_decouper(src[len(d_src.rstrip("/")) + 1:]))
                if self._confirme(cand, e):
                    return cand, _("dossier déjà appris")
        # 2. chemin exact
        if self._confirme(e["chemin"], e):
            return e["chemin"], _("même emplacement")
        # 3. meme dossier par defaut ici (Documents, Telechargements, NAS... meme d'un systeme a l'autre)
        connus = dossiers_connus(self.params)
        if e.get("connu") in connus:
            cand = os.path.join(connus[e["connu"]], *_decouper(e["relatif_connu"]))
            if self._confirme(cand, e):
                return cand, _("{dossier} de ce PC", dossier=dict(CONNUS).get(e["connu"], e["connu"]))
        # 4. dossier utilisateur transpose (C:\Users\A -> C:\Users\B ou /home/b)
        if e.get("relatif_maison"):
            cand = os.path.join(os.path.expanduser("~"), *_decouper(e["relatif_maison"]))
            if self._confirme(cand, e):
                return cand, _("dossier utilisateur de ce PC")
        # 5. emplacements ajoutes en mode avance
        if e.get("relatif_racine"):
            for r in self.params.get("racines", []):
                cand = os.path.join(r, *_decouper(e["relatif_racine"]))
                if self._confirme(cand, e):
                    return cand, _("sous {dossier}", dossier=r)
        return None, None

    def retrouver_tous(self, machine, fichiers, arret=lambda: False, delai=None, progression=None):
        """Toute la cascade pour une liste de fichiers. Les etapes directes d'abord, puis UN SEUL
        parcours des dossiers pour tous les fichiers manquants : par le nom (confirme par l'empreinte),
        sinon par la taille puis l'empreinte (fichier renomme). Limite : LIMITE_FICHIERS et `delai`.
        Renvoie [(chemin ou None, comment)] dans l'ordre des fichiers."""
        res = [self.retrouver_direct(machine, e) for e in fichiers]
        manquants = [i for i, (c, _x) in enumerate(res) if not c]
        if progression:
            for i, (c, cm) in enumerate(res):
                progression(i, c, cm or "")
        if not manquants:
            return res
        par_nom, par_taille = {}, {}
        for i in manquants:
            par_nom.setdefault(fichiers[i]["nom"].lower(), []).append(i)
            if fichiers[i].get("taille") is not None and fichiers[i].get("empreinte"):
                par_taille.setdefault(fichiers[i]["taille"], []).append(i)
        debut, n, vus = time.monotonic(), 0, set()
        complet = True
        for r in self.racines():
            for base, dossiers, noms in os.walk(r):
                nb = _norm(base)
                if nb in vus:
                    dossiers[:] = []
                    continue
                vus.add(nb)
                dossiers[:] = [d for d in dossiers if not d.startswith((".", "$", "~")) and d not in IGNORES]
                for f in noms:
                    n += 1
                    fl = f.lower()
                    if fl in par_nom:
                        p = os.path.join(base, f)
                        for i in list(par_nom[fl]):
                            if not res[i][0] and self._confirme(p, fichiers[i]):
                                res[i] = (p, _("retrouvé par son nom"))
                                par_nom[fl].remove(i)
                                progression and progression(i, p, res[i][1])
                    if par_taille and fl.endswith(".pdf"):
                        p = os.path.join(base, f)
                        try:
                            t = os.path.getsize(p)
                        except OSError:
                            continue
                        for i in par_taille.get(t, []):
                            if not res[i][0] and empreinte(p) == fichiers[i]["empreinte"]:
                                res[i] = (p, _("renommé, retrouvé par son contenu"))
                                progression and progression(i, p, res[i][1])
                if all(res[i][0] for i in manquants):
                    return res
                if arret() or n > LIMITE_FICHIERS or (delai and time.monotonic() - debut > delai):
                    complet = False
                    break
            if not complet:
                break
        for i in manquants:
            if not res[i][0]:
                res[i] = (None, _("introuvable") if complet else _("introuvable (recherche limitée)"))
                progression and progression(i, None, res[i][1])
        return res

    def apprendre_depuis(self, machine, e, trouve):
        """Retient dossier source -> dossier trouve, et aussi la racine commune : si
        C:/Users/A/Documents/Ordo est en fait /home/b/Documents/Ordo, on apprend aussi
        C:/Users/A -> /home/b, qui servira pour tous les autres fichiers de A."""
        src = e["chemin"].replace("\\", "/")
        d_src = src.rsplit("/", 1)[0]
        d_ici = os.path.dirname(trouve)
        if _norm(d_src) == _norm(d_ici):
            return
        self.apprendre(machine, d_src, d_ici)
        a, b = _decouper(d_src), _decouper(d_ici.replace("\\", "/"))
        k = 0
        while k < min(len(a), len(b)) - 1 and a[-1 - k].lower() == b[-1 - k].lower():
            k += 1
        if k:
            pa, pb = d_src, d_ici
            for _x in range(k):
                pa, pb = pa.rsplit("/", 1)[0], os.path.dirname(pb)
            if pa and pb and _norm(pa) != _norm(pb):
                self.apprendre(machine, pa, pb)


def date_fr(iso):
    """'2026-10-22T18:12' -> '22/10 à 18h12' (avec l'annee si ce n'est pas l'annee en cours)."""
    try:
        d = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return _('date inconnue')
    if d.year == datetime.date.today().year:
        return _("{jour:02d}/{mois:02d} à {heure}h{minute:02d}", jour=d.day, mois=d.month, heure=d.hour, minute=d.minute)
    return _("{jour:02d}/{mois:02d}/{annee} à {heure}h{minute:02d}", jour=d.day, mois=d.month, annee=d.year,
             heure=d.hour, minute=d.minute)


def nb_fichiers(n):
    return _("{n} fichier", n=n) if n <= 1 else _("{n} fichiers", n=n)


def session_de(params):
    """Session rangee sur le Drive (ou en local si aucun Drive n'est indique)."""
    p = params.chemin_session()
    return Session(params, p, os.path.join(os.path.dirname(p), "correspondances.json"))
