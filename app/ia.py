"""Assistant IA : appels a Claude (Anthropic) ou Gemini (Google) avec la clef API de l'utilisateur.

Rien ne part sans un clic. Avant chaque envoi, les donnees sensibles reperees dans le texte (IBAN, carte
bancaire, numero de securite sociale, numero fiscal, mot de passe...) sont signalees : l'utilisateur confirme ou
renonce. Le modele est choisi automatiquement si celui des reglages n'existe plus chez le fournisseur.
"""
import base64, json, re, urllib.error, urllib.request

from .langue import _

CLAUDE_API = "https://api.anthropic.com/v1"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
MODELE_CLAUDE = "claude-sonnet-5-5"
MODELE_GEMINI = "gemini-2.5-flash"
_modeles_trouves = {}
DELAI = 180                 # secondes d'attente d'une reponse (le test des clefs met moins)
_entete_claude = {}         # clef -> en-tetes qui marchent (x-api-key ou Authorization: Bearer)


class ErreurIA(Exception):
    pass


# ------------------------------------------------------------------ donnees sensibles
def _luhn(chiffres):
    s, double = 0, False
    for c in reversed(chiffres):
        n = int(c) * (2 if double else 1)
        s += n - 9 if n > 9 else n
        double = not double
    return s % 10 == 0


def _iban_valide(iban):
    i = iban[4:] + iban[:4]
    n = "".join(str(int(c, 36)) for c in i)
    return int(n) % 97 == 1


def _nir_valide(nir):
    corps, cle = nir[:13], nir[13:]
    corps = corps.upper().replace("2A", "19").replace("2B", "18")
    try:
        return 97 - int(corps) % 97 == int(cle)
    except ValueError:
        return False


def donnees_sensibles(texte):
    """Liste de (genre, extrait masque) reperes dans le texte."""
    out = []
    t = texte or ""
    for m in re.finditer(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b", t):
        brut = m.group().replace(" ", "")
        if 15 <= len(brut) <= 34 and _iban_valide(brut):
            out.append((_("IBAN (coordonnées bancaires)"), brut[:4] + " ... " + brut[-4:]))
    for m in re.finditer(r"\b(?:\d[ -]?){13,19}\b", t):
        ch = re.sub(r"\D", "", m.group())
        if 13 <= len(ch) <= 19 and ch[0] in "3456" and _luhn(ch):
            out.append((_("Numéro de carte bancaire"), "**** " + ch[-4:]))
    for m in re.finditer(r"\b([12])[ ]?(\d{2})[ ]?(\d{2})[ ]?(\d{2}|2A|2B)[ ]?(\d{3})[ ]?(\d{3})[ ]?(\d{2})\b", t):
        nir = "".join(m.groups())
        if _nir_valide(nir):
            out.append((_("Numéro de sécurité sociale"), nir[:1] + " ** ** ** *** *** " + nir[-2:]))
    for m in re.finditer(r"(?i)(?:num[ée]ro fiscal|n° fiscal|SPI)\D{0,12}([0-3]\d(?:[ ]?\d){11})\b", t):
        out.append((_("Numéro fiscal"), m.group(1)[:2] + " ... "))
    for m in re.finditer(r"(?i)\b(mot de passe|password|code confidentiel|code secret)\b\s*[:=]\s*\S+", t):
        out.append((_("Mot de passe ou code"), m.group(1) + " : ****"))
    vus, uniques = set(), []
    for g, x in out:
        if (g, x) not in vus:
            vus.add((g, x))
            uniques.append((g, x))
    return uniques


def confirmer_envoi(parent, texte, moteur_nom):
    """Rappel avant l'envoi a l'IA si des donnees sensibles sont reperees. True = on envoie."""
    trouves = donnees_sensibles(texte)
    if not trouves:
        return True
    from PySide6.QtWidgets import QMessageBox
    liste = "\n".join(f"  • {g} : {x}" for g, x in trouves[:8])
    if len(trouves) > 8:
        liste += "\n  • ..."
    r = QMessageBox.warning(parent, _("Données sensibles détectées"),
                            _("Ce document semble contenir des données sensibles :\n\n{liste}\n\nÊtes-vous sûr de vouloir "
                              "l'envoyer à l'IA ({moteur}) ?", liste=liste, moteur=moteur_nom),
                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    return r == QMessageBox.Yes


# ------------------------------------------------------------------ appels
def nettoyer_clef(c):
    """Retire espaces, retours a la ligne et guillemets venus du copier-coller."""
    return re.sub(r"[\s\"'«»]+", "", c or "")


def moteurs(params):
    """Moteurs utilisables dans l'ordre de preference : [("claude", clef), ("gemini", clef)]."""
    choix = params.get("ia_moteur", "claude")
    ordre = ["gemini", "claude"] if choix == "gemini" else ["claude", "gemini"]
    return [(m, nettoyer_clef(params.get("clef_" + m, ""))) for m in ordre if nettoyer_clef(params.get("clef_" + m, ""))]


def nom_moteur(params):
    m = moteurs(params)
    return {"claude": "Claude", "gemini": "Gemini"}.get(m[0][0], "?") if m else "?"


def disponible(params):
    return bool(moteurs(params))


def _http(url, corps=None, entetes=None, methode=None, delai=None):
    delai = delai or DELAI
    r = urllib.request.Request(url, data=json.dumps(corps).encode() if corps is not None else None,
                               method=methode or ("POST" if corps is not None else "GET"))
    r.add_header("Content-Type", "application/json")
    for k, v in (entetes or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=delai) as f:
            return json.loads(f.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode("utf-8", "replace"))
            msg = (d.get("error") or {}).get("message") or str(d)
        except ValueError:
            msg = str(e)
        err = ErreurIA(f"{e.code} : {msg}")
        err.code = e.code
        raise err
    except OSError as e:
        raise ErreurIA(_("Service injoignable : {raison}", raison=e))


def _entetes_claude(clef, autre=False):
    base = {"anthropic-version": "2023-06-01"}
    bearer = _entete_claude.get(clef) == "bearer"
    if autre:
        bearer = not bearer
    return dict(base, **({"Authorization": f"Bearer {clef}"} if bearer else {"x-api-key": clef}))


def _modele_claude(clef, params, forcer=False):
    if not forcer:
        return params.get("ia_modele_claude") or _modeles_trouves.get("claude") or MODELE_CLAUDE
    d = _http(f"{CLAUDE_API}/models?limit=100", entetes=_entetes_claude(clef))
    ids = [m["id"] for m in d.get("data", [])]
    for famille in ("sonnet", "opus", "haiku"):
        for i in ids:                                  # la liste est triee du plus recent au plus ancien
            if famille in i:
                _modeles_trouves["claude"] = i
                return i
    raise ErreurIA(_("Aucun modèle Claude disponible avec cette clef."))


def _modele_gemini(clef, params, forcer=False):
    if not forcer:
        return params.get("ia_modele_gemini") or _modeles_trouves.get("gemini") or MODELE_GEMINI
    d = _http(f"{GEMINI_API}/models?pageSize=200&key={clef}")
    ids = [m["name"].split("/")[-1] for m in d.get("models", [])
           if "generateContent" in m.get("supportedGenerationMethods", [])]
    candidats = [i for i in ids if "flash" in i and "lite" not in i and "exp" not in i and "preview" not in i] or \
                [i for i in ids if i.startswith("gemini")]
    if not candidats:
        raise ErreurIA(_("Aucun modèle Gemini disponible avec cette clef."))

    def version(i):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", i)
        return float(m.group(1)) if m else 0
    _modeles_trouves["gemini"] = max(candidats, key=version)
    return _modeles_trouves["gemini"]


def _claude(clef, params, consignes, texte, images, max_jetons):
    contenu = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.b64encode(i).decode()}} for i in images or []]
    contenu.append({"type": "text", "text": texte})
    corps = lambda m: {"model": m, "max_tokens": max_jetons, "system": consignes,
                       "messages": [{"role": "user", "content": contenu}]}
    forcer, autre_entete = False, False
    for _essai in range(3):
        modele = _modele_claude(clef, params, forcer=forcer)
        try:
            d = _http(f"{CLAUDE_API}/messages", corps(modele), _entetes_claude(clef, autre_entete))
            if autre_entete:                           # cette clef veut l'autre en-tete : on s'en souvient
                _entete_claude[clef] = "bearer" if _entete_claude.get(clef) != "bearer" else "x-api-key"
            return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        except ErreurIA as e:
            code = getattr(e, "code", 0)
            if code == 404 and not forcer:
                forcer = True                          # modele retire : on prend le plus recent
                continue
            if code in (401, 403) and not autre_entete:
                autre_entete = True                    # autre facon de presenter la clef
                continue
            if code in (401, 403):
                raise ErreurIA(_("Clef Claude refusée ({detail}). Vérifiez-la dans Edition › Préférences › IA : "
                                 "elle commence par « sk-ant- » et doit être copiée en entier depuis console.anthropic.com "
                                 "(Clés API), avec du crédit sur le compte.", detail=str(e)[:160]))
            raise


def _gemini(clef, params, consignes, texte, images, max_jetons, json_attendu):
    parts = [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(i).decode()}} for i in images or []]
    parts.append({"text": texte})
    corps = {"system_instruction": {"parts": [{"text": consignes}]}, "contents": [{"role": "user", "parts": parts}],
             "generationConfig": {"maxOutputTokens": max_jetons}}
    if json_attendu:
        corps["generationConfig"]["responseMimeType"] = "application/json"
    for essai in (False, True):
        modele = _modele_gemini(clef, params, forcer=essai)
        try:
            d = _http(f"{GEMINI_API}/models/{modele}:generateContent?key={clef}", corps)
            cands = d.get("candidates") or []
            if not cands:
                raise ErreurIA(_("Gemini n'a pas répondu ({raison}).", raison=(d.get("promptFeedback") or {}).get("blockReason", "?")))
            return "".join(p.get("text", "") for p in (cands[0].get("content") or {}).get("parts", []))
        except ErreurIA as e:
            if getattr(e, "code", 0) == 404 and not essai:
                continue
            if getattr(e, "code", 0) in (400, 403) and "API key" in str(e):
                raise ErreurIA(_("Clef Gemini refusée : vérifiez-la dans Edition › Préférences › IA."))
            raise


def demander(params, consignes, texte, images=None, json_attendu=False, max_jetons=4000):
    """Texte (ou objet JSON si json_attendu) renvoye par le premier moteur qui repond."""
    ms = moteurs(params)
    if not ms:
        raise ErreurIA(_("Aucune clef d'IA : renseignez votre clef Claude ou Gemini dans Edition › Préférences › IA."))
    if json_attendu:
        consignes += "\n\nRéponds uniquement par un objet JSON valide, sans texte autour ni balises de code."
    derniere = None
    from .journal import ecrire
    for m, clef in ms:
        import time as _t
        debut = _t.time()
        try:
            r = _claude(clef, params, consignes, texte, images, max_jetons) if m == "claude" else \
                _gemini(clef, params, consignes, texte, images, max_jetons, json_attendu)
            ecrire("IA " + m, f"réponse en {_t.time() - debut:.1f} s, modèle {_modeles_trouves.get(m, '?')}, "
                              f"{len(texte)} car. envoyés{', ' + str(len(images)) + ' image(s)' if images else ''}")
            return lire_json(r) if json_attendu else r.strip()
        except ErreurIA as e:
            ecrire("IA " + m, f"✕ après {_t.time() - debut:.1f} s : {e}")
            derniere = e
            if params.get("ia_moteur") != "deux":
                break
    raise derniere


def lire_json(texte):
    t = (texte or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        m = re.search(r"[\[{].*[\]}]", t, re.S)
        if m:
            try:
                return json.loads(m.group())
            except ValueError:
                pass
    raise ErreurIA(_("Réponse de l'IA illisible."))


def texte_document(doc, max_car=120000):
    """Texte du PDF (pages numerotees) pour l'IA, tronque si tres long."""
    morceaux, n = [], 0
    for i, p in enumerate(doc):
        t = p.get_text("text").strip()
        if t:
            morceaux.append(f"--- Page {i + 1} ---\n{t}")
            n += len(t)
            if n > max_car:
                morceaux.append(_("[... document tronqué ...]"))
                break
    return "\n\n".join(morceaux)
