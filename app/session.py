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
import datetime, hashlib, json, os

LIMITE_FICHIERS = 200_000          # garde-fou pour les recherches dans les racines


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

    # ------------------------------------------------------------ racines de cette machine
    def racines(self):
        r = [x for x in self.params.get("racines", []) if x and os.path.isdir(x)]
        maison = os.path.expanduser("~")
        if not any(_norm(x) == _norm(maison) for x in r):
            r.insert(0, maison)
        if self.params.get("drive") and os.path.isdir(self.params["drive"]) and \
                not any(_norm(x) == _norm(self.params["drive"]) for x in r):
            r.append(self.params["drive"])
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

    def ecrire(self, ouverts):
        """ouverts = [(chemin, page, zoom)] des documents ouverts ici."""
        maison = os.path.expanduser("~")
        fichiers = []
        for chemin, page, zoom in ouverts:
            if not chemin or not os.path.exists(chemin):
                continue
            e = {"chemin": chemin, "nom": os.path.basename(chemin), "taille": os.path.getsize(chemin),
                 "empreinte": empreinte(chemin), "page": page, "zoom": zoom,
                 "relatif_maison": _relatif(chemin, maison)}
            for r in self.racines():
                rel = _relatif(chemin, r)
                if rel:
                    e["racine"], e["relatif_racine"] = r, rel
                    break
            fichiers.append(e)
        d = self.lire()
        d[self.params["machine"]] = {"maj": datetime.datetime.now().isoformat(timespec="minutes"),
                                     "maison": maison, "fichiers": fichiers}
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

    # ------------------------------------------------------------ correspondances apprises
    def _corresp(self):
        try:
            with open(self.chemin_corresp, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def apprendre(self, machine, dossier_source, dossier_ici):
        c = self._corresp()
        cle = f"{machine} -> {self.params['machine']}"
        c.setdefault(cle, {})[dossier_source] = dossier_ici
        try:
            with open(self.chemin_corresp, "w", encoding="utf-8") as f:
                json.dump(c, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    # ------------------------------------------------------------ recherche
    def _confirme(self, chemin, e):
        if not os.path.isfile(chemin):
            return False
        if e.get("taille") is not None and os.path.getsize(chemin) != e["taille"]:
            return False
        return not e.get("empreinte") or empreinte(chemin) == e["empreinte"]

    def retrouver_rapide(self, machine, e):
        """Etapes 0 a 4. Renvoie (chemin, comment) ou (None, None)."""
        src = e["chemin"]
        # 0. correspondance apprise (dossier ou dossier parent)
        appris = self._corresp().get(f"{machine} -> {self.params['machine']}", {})
        for d_src, d_ici in sorted(appris.items(), key=lambda x: -len(x[0])):
            if src.replace("\\", "/").startswith(d_src.replace("\\", "/") + "/"):
                rel = src.replace("\\", "/")[len(d_src.replace("\\", "/")) + 1:]
                cand = os.path.join(d_ici, *_decouper(rel))
                if self._confirme(cand, e):
                    return cand, "dossier déjà appris"
        # 1. chemin exact
        if self._confirme(src, e):
            return src, "même emplacement"
        # 2. dossier utilisateur transpose
        if e.get("relatif_maison"):
            cand = os.path.join(os.path.expanduser("~"), *_decouper(e["relatif_maison"]))
            if self._confirme(cand, e):
                return cand, "dossier utilisateur de ce PC"
        # 3. meme chemin relatif sous les racines declarees
        if e.get("relatif_racine"):
            for r in self.racines():
                cand = os.path.join(r, *_decouper(e["relatif_racine"]))
                if self._confirme(cand, e):
                    return cand, f"sous {r}"
        # 4. recherche par nom dans les racines, confirmee par l'empreinte
        n = 0
        for r in self.racines():
            for base, dossiers, fichiers in os.walk(r):
                dossiers[:] = [d for d in dossiers if not d.startswith((".", "$")) and d not in ("AppData", "node_modules")]
                n += len(fichiers)
                if e["nom"] in fichiers:
                    cand = os.path.join(base, e["nom"])
                    if self._confirme(cand, e):
                        return cand, "retrouvé par son nom"
                if n > LIMITE_FICHIERS:
                    break
        return None, None

    def retrouver_par_empreinte(self, e, arret=lambda: False):
        """Etape 5 : fichier renomme -> meme taille et meme empreinte."""
        if not e.get("empreinte") or e.get("taille") is None:
            return None
        n = 0
        for r in self.racines():
            for base, dossiers, fichiers in os.walk(r):
                dossiers[:] = [d for d in dossiers if not d.startswith((".", "$")) and d not in ("AppData", "node_modules")]
                for f in fichiers:
                    n += 1
                    if arret() or n > LIMITE_FICHIERS:
                        return None
                    if not f.lower().endswith(".pdf"):
                        continue
                    p = os.path.join(base, f)
                    try:
                        if os.path.getsize(p) == e["taille"] and empreinte(p) == e["empreinte"]:
                            return p
                    except OSError:
                        pass
        return None

    def apprendre_depuis(self, machine, e, trouve):
        """Retient dossier source -> dossier trouve (les autres fichiers du meme dossier suivront)."""
        src = e["chemin"].replace("\\", "/")
        d_src = src.rsplit("/", 1)[0]
        d_ici = os.path.dirname(trouve)
        if _norm(d_src) != _norm(d_ici):
            self.apprendre(machine, d_src, d_ici)


def date_fr(iso):
    """'2026-10-22T18:12' -> '22/10 à 18h12' (avec l'annee si ce n'est pas l'annee en cours)."""
    try:
        d = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return "date inconnue"
    a = "" if d.year == datetime.date.today().year else f"/{d.year}"
    return f"{d.day:02d}/{d.month:02d}{a} à {d.hour}h{d.minute:02d}"


def nb_fichiers(n):
    return f"{n} fichier" + ("s" if n > 1 else "")


def session_de(params):
    """Session rangee sur le Drive (ou en local si aucun Drive n'est indique)."""
    p = params.chemin_session()
    return Session(params, p, os.path.join(os.path.dirname(p), "correspondances.json"))
