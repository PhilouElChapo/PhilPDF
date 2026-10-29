"""Assistant IA : appels a Claude (Anthropic) ou Gemini (Google) avec la clef API de l'utilisateur.

Rien ne part sans un clic. Avant chaque envoi, les donnees sensibles reperees dans le texte (IBAN, carte
bancaire, numero de securite sociale, numero fiscal, mot de passe...) sont signalees : l'utilisateur confirme ou
renonce. Le modele est choisi automatiquement si celui des reglages n'existe plus chez le fournisseur.
"""
import base64, json, re, threading, time, urllib.error, urllib.request

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


# ------------------------------------------------------------------ suivi en direct de l'envoi
_suivi = threading.local()


def suivre(fonction):
    """fonction(texte) recevra, pour ce fil d'execution, chaque etape de l'envoi (connexion, envoi, reponse, refus)."""
    _suivi.fn = fonction


def rapporter(texte):
    fn = getattr(_suivi, "fn", None)
    if fn:
        try:
            fn(texte)
        except Exception:
            pass


def _taille(n):
    return f"{n / 1048576:.1f} Mo".replace(".", ",") if n >= 1048576 else f"{max(1, n // 1024)} Ko"


def expliquer_refus(code, msg):
    """Phrase claire pour les refus courants (quota, surcharge) ; '' sinon."""
    if code == 429:
        m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", msg)
        quand = ""
        if m:
            h, mi, s = int(m.group(1) or 0), int(m.group(2) or 0), float(m.group(3))
            quand = _(" Réessayer dans {d}.", d=(f"{h} h {mi:02d} min" if h else f"{mi} min {int(s):02d} s" if mi else f"{int(s)} s"))
        if "limit: 0" in msg:
            return _("Quota à 0 : la clef gratuite n'a pas droit à ce modèle. Il faut activer la facturation du projet "
                     "Google (aistudio.google.com › Facturation).") + quand
        if "per day" in msg or "PerDay" in msg:
            return _("Quota du jour épuisé.") + quand
        return _("Trop de demandes, quota de la minute atteint.") + quand
    if code in (500, 502, 503, 504):
        return _("Service surchargé ou en panne passagère ({code}).", code=code)
    return ""


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


MOTEUR_FORCE = None        # IA choisie pour une demande (fenetre de consigne) ; sinon celle des Preferences


def moteurs(params):
    """Moteurs utilisables dans l'ordre de preference : [("claude", clef), ("gemini", clef)]."""
    choix = MOTEUR_FORCE or params.get("ia_moteur", "claude")
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
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(r, timeout=delai) as f:
            brut = f.read()
            if corps is not None:
                rapporter(_("← Réponse acceptée (code {c}) en {s} s, {t} reçus", c=f.status,
                            s=f"{time.monotonic() - t0:.1f}".replace(".", ","), t=_taille(len(brut))))
            return json.loads(brut.decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode("utf-8", "replace"))
            msg = (d.get("error") or {}).get("message") or str(d)
        except ValueError:
            msg = str(e)
        clair = expliquer_refus(e.code, msg)
        rapporter(_("✕ Refusé (code {c}) après {s} s : {m}", c=e.code, s=f"{time.monotonic() - t0:.1f}".replace(".", ","),
                    m=clair or msg[:200]))
        err = ErreurIA(f"{e.code} : {msg}")
        err.code, err.clair = e.code, clair
        raise err
    except OSError as e:
        rapporter(_("✕ Pas de réponse après {s:.0f} s : {r}", s=time.monotonic() - t0, r=e))
        err = ErreurIA(_("Service injoignable : {raison}", raison=e))
        err.delai = "timed out" in str(e).lower() or isinstance(e, TimeoutError)
        raise err


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


TRANSITOIRES = (429, 500, 502, 503, 504)
dernier = {}                                   # qui a vraiment repondu a la derniere demande (moteur, modele)       # surcharge ou panne passagere chez le fournisseur


def _modeles_gemini_secours(clef):
    """Autres modeles Gemini a essayer quand le premier est surcharge : flash recents, puis flash-lite, puis pro."""
    if "gemini_secours" in _modeles_trouves:
        return _modeles_trouves["gemini_secours"]
    try:
        d = _http(f"{GEMINI_API}/models?pageSize=200&key={clef}", delai=20)
        ids = [m["name"].split("/")[-1] for m in d.get("models", [])
               if "generateContent" in m.get("supportedGenerationMethods", [])]
    except ErreurIA:
        ids = []

    def version(i):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", i)
        return float(m.group(1)) if m else 0
    stables = [i for i in ids if i.startswith("gemini") and "exp" not in i and "preview" not in i
               and not any(x in i for x in ("embedding", "tts", "image", "audio", "live"))]
    flash = sorted([i for i in stables if "flash" in i and "lite" not in i], key=version, reverse=True)
    lite = sorted([i for i in stables if "flash-lite" in i], key=version, reverse=True)
    pro = sorted([i for i in stables if "pro" in i], key=version, reverse=True)
    _modeles_trouves["gemini_secours"] = (flash + lite + pro)[:5] or ["gemini-flash-latest", "gemini-flash-lite-latest"]
    return _modeles_trouves["gemini_secours"]


def _claude(clef, params, consignes, texte, images, max_jetons):
    contenu = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.b64encode(i).decode()}} for i in images or []]
    contenu.append({"type": "text", "text": texte})
    corps = lambda m: {"model": m, "max_tokens": max_jetons, "system": consignes,
                       "messages": [{"role": "user", "content": contenu}]}
    forcer, autre_entete = False, False
    for _essai in range(3):
        modele = _modele_claude(clef, params, forcer=forcer)
        rapporter(_("→ Envoi à Claude, modèle {m}, attente de la réponse...", m=modele))
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
    from .journal import ecrire
    essais = [_modele_gemini(clef, params)]
    deja_liste = False
    while essais:
        modele = essais.pop(0)
        rapporter(_("→ Envoi à Gemini, modèle {m}{i}, attente de la réponse...", m=modele,
                    i=_(" ({n} image(s))", n=len(images)) if images else ""))
        try:
            d = _http(f"{GEMINI_API}/models/{modele}:generateContent?key={clef}", corps)
            cands = d.get("candidates") or []
            if not cands:
                raise ErreurIA(_("Gemini n'a pas répondu ({raison}).", raison=(d.get("promptFeedback") or {}).get("blockReason", "?")))
            _modeles_trouves["gemini"] = modele
            return "".join(p.get("text", "") for p in (cands[0].get("content") or {}).get("parts", []))
        except ErreurIA as e:
            code = getattr(e, "code", 0)
            if code in (400, 403) and "API key" in str(e):
                raise ErreurIA(_("Clef Gemini refusée : vérifiez-la dans Edition › Préférences › IA."))
            # modele inconnu, surcharge ou delai depasse : on essaie un autre modele Gemini
            if code == 404 or code in TRANSITOIRES or getattr(e, "delai", False):
                ecrire("IA gemini", f"modèle {modele} : {e} → essai d'un autre modèle")
                if not deja_liste:
                    deja_liste = True
                    essais += [m for m in _modeles_gemini_secours(clef) if m != modele and m not in essais][:3]
                if essais:
                    continue
            raise


def modeles_image_gemini(clef):
    """Modeles Gemini qui savent rendre une image modifiee (les plus recents d'abord, stables avant les apercus)."""
    if "gemini_image" in _modeles_trouves:
        return _modeles_trouves["gemini_image"]
    try:
        d = _http(f"{GEMINI_API}/models?pageSize=200&key={clef}", delai=20)
        ids = [m["name"].split("/")[-1] for m in d.get("models", [])
               if "generateContent" in m.get("supportedGenerationMethods", [])]
    except ErreurIA:
        ids = []

    def rang(i):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", i)
        return ("preview" not in i and "exp" not in i, float(m.group(1)) if m else 0, "pro" not in i)
    img = sorted([i for i in ids if i.startswith("gemini") and "image" in i and "imagen" not in i], key=rang, reverse=True)
    _modeles_trouves["gemini_image"] = img or ["gemini-2.5-flash-image", "gemini-2.5-flash-image-preview"]
    return _modeles_trouves["gemini_image"]


def retoucher_image(params, png, consigne, zones_png=None, delai=240):
    """Envoie l'image (PNG) et la consigne a Gemini, qui renvoie l'image modifiee (octets PNG ou JPEG).
    zones_png : la meme image avec les zones entourees et numerotees (la consigne dit quoi faire de chacune).
    Claude ne sait pas produire d'image : seul Gemini est utilise ici."""
    clef = nettoyer_clef(params.get("clef_gemini", ""))
    if not clef:
        raise ErreurIA(_("Il faut une clef Gemini (Edition › Préférences › IA) : Claude ne sait pas modifier une image."))
    parts = [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}}]
    if zones_png:
        parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(zones_png).decode()}})
    parts.append({"text": consigne})
    corps = {"contents": [{"role": "user", "parts": parts}],
             "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
    from .journal import ecrire
    derniere = None
    rapporter(_("Recherche des modèles d'image proposés par votre clef Gemini..."))
    liste = modeles_image_gemini(clef)[:4]
    rapporter(_("Modèles à essayer, dans l'ordre : {l}", l=", ".join(liste)))
    poids = len(png) + len(zones_png or b"")
    refus = []
    for modele in liste:
        rapporter(_("→ Envoi à {m} : image {t}{z}, consigne de {n} caractères. Gemini travaille "
                    "(souvent 10 à 60 s)...", m=modele, t=_taille(poids),
                    z=_(" + plan des zones") if zones_png else "", n=len(consigne)))
        try:
            t0 = time.monotonic()
            d = _http(f"{GEMINI_API}/models/{modele}:generateContent?key={clef}", corps, delai=delai)
            for c in d.get("candidates") or []:
                for p in (c.get("content") or {}).get("parts", []):
                    data = p.get("inline_data") or p.get("inlineData")
                    if data and data.get("data"):
                        ecrire("IA gemini", f"image modifiée en {time.monotonic() - t0:.1f} s, modèle {modele}")
                        rapporter(_("✓ Image modifiée reçue de {m}.", m=modele))
                        dernier.update(moteur="gemini", modele=modele)
                        return base64.b64decode(data["data"])
            texte = " ".join(p.get("text", "") for c in d.get("candidates") or [] for p in (c.get("content") or {}).get("parts", []))
            raison = (d.get("promptFeedback") or {}).get("blockReason") or texte.strip()[:200] or "?"
            raise ErreurIA(_("Gemini n'a pas renvoyé d'image ({raison}).", raison=raison))
        except ErreurIA as e:
            code = getattr(e, "code", 0)
            if code in (400, 403) and "API key" in str(e):
                raise ErreurIA(_("Clef Gemini refusée : vérifiez-la dans Edition › Préférences › IA."))
            ecrire("IA gemini", f"image, modèle {modele} : {e}")
            derniere = e
            refus.append((modele, getattr(e, "clair", "") or str(e)[:160]))
            if code == 404 or code in TRANSITOIRES or getattr(e, "delai", False):
                if modele != liste[-1]:
                    rapporter(_("→ On essaie le modèle suivant."))
                continue
            rapporter(_("✕ {e}", e=str(e)[:300]))
            raise
    if refus:
        raise ErreurIA(_("Gemini a refusé la demande sur les modèles d'image essayés :") + "\n" +
                       "\n".join(f"• {m} : {r}" for m, r in refus))
    raise derniere or ErreurIA(_("Aucun modèle Gemini d'image disponible avec cette clef."))


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
            dernier.update(moteur=m, modele=_modeles_trouves.get(m, "?"), secours=m != ms[0][0], premier=ms[0][0])
            ecrire("IA " + m, f"réponse en {_t.time() - debut:.1f} s, modèle {_modeles_trouves.get(m, '?')}, "
                              f"{len(texte)} car. envoyés{', ' + str(len(images)) + ' image(s)' if images else ''}")
            return lire_json(r) if json_attendu else r.strip()
        except ErreurIA as e:
            ecrire("IA " + m, f"✕ après {_t.time() - debut:.1f} s : {e}")
            derniere = e
            passager = getattr(e, "code", 0) in TRANSITOIRES or getattr(e, "delai", False)
            if params.get("ia_moteur") != "deux" and not passager:
                break                                    # surcharge passagere : on passe a l'autre IA si elle a une clef
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
