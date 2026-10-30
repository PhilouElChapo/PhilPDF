"""Nettoyage du carnet d'adresses : doublons, noms a remettre en forme, prenom / nom de famille, adresses invalides.
Rien n'est change sans accord : nettoyer() fait des propositions, appliquer() applique celles cochees."""
import re
import time
import unicodedata

# Prenoms courants (France et voisins) : servent a reconnaitre le prenom dans « Perat Valentin » ou « Valentin Perat »
PRENOMS = set("""
adam adele adrien agathe agnes alain alban albert alexandra alexandre alexis alfred alice alicia aline alix amandine
amaury ambre amelie anais andre andrea andree ange angele angelique anne annabelle anne-marie anne-sophie annick annie
anthony antoine antoinette antonin apolline arnaud arthur audrey aurelie aurelien axel axelle barbara bastien beatrice
benedicte benjamin benoit bernadette bernard bertrand blandine brigitte bruno camille capucine carine carole caroline
catherine cecile cedric celine chantal charles charlotte chloe christelle christian christine christophe claire clara
claude claudine clement clemence colette coralie corinne cyril cyrille damien daniel daniele danielle david delphine
denis denise didier dominique dorian dylan edith edouard eliane elie eliott elisa elisabeth elise ella elodie eloise
emile emilie emma emmanuel emmanuelle enzo eric estelle ethan etienne eugenie eva evelyne fabien fabienne fabrice
fanny felix fernand fernande flavie florence florian franck francine francis francois francoise frederic frederique
gabin gabriel gabrielle gael gaelle gaetan gaspard genevieve geoffrey georges gerald gerard germaine gilbert gilles
ginette gisele grace gregoire gregory guillaume gustave guy guylaine helene henri herve hugo hugues ines irene isabelle
jacqueline jacques jade jean jean-baptiste jean-claude jean-francois jean-louis jean-luc jean-marc jean-marie
jean-michel jean-paul jean-pierre jeanne jeannine jeremie jeremy jerome joel joelle johan johanna jonathan jordan
joseph josette josiane josephine jules julia julie julien juliette justine karine kevin laetitia laura laure laurence
laurent lea lea leila leo leon leonie lilian liliane lina lionel lisa loic lou louis louise luc luca lucas lucie
lucien lucienne ludovic lydie madeleine maelle magali manon marc marcel marcelle margaux margot marguerite maria
marianne marie marie-claire marie-france marie-paule marie-pierre marie-therese marine marion martine mathias mathieu
mathilde matthieu maud maurice max maxime melanie melissa michel michele micheline mickael mireille monique morgane
muriel myriam nadia nadine nathalie nathan nicolas nicole noah noe noel noemie oceane odette odile olivia olivier
pascal pascale patrice patricia patrick paul paule paulette pauline perrine philippe pierre pierrette quentin raphael
raphaelle raymond raymonde regine remi remy renaud rene renee richard robert robin roger roland romain romane rose
sabine sacha samuel sandra sandrine sarah sebastien serge severine simon simone solange solene sophie stephane
stephanie suzanne sylvain sylvie tatiana theo theodore therese thibault thibaut thierry thomas timothee tristan valentin
valentine valerie vanessa veronique victor victoire vincent virginie vivien vivienne xavier yann yannick yolande yves
yvette yvonne zoe ahmed ali amine fatima karim mohamed nadir rachid samir sofiane yasmine leila mehdi nora omar
giovanni giuseppe marco paolo luigi francesco antonio maria rosa carlos jose juan manuel pedro miguel ana carmen
hans klaus peter stefan andreas michael john james william robert mary elizabeth patricia jennifer linda susan
""".split())

PARTICULES = {"de", "du", "des", "la", "le", "van", "von", "der", "di", "da", "del", "d'", "mac", "mc"}


def _sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def est_prenom(mot):
    m = _sans_accents(mot).strip(".")
    return m in PRENOMS or (("-" in m) and all(x in PRENOMS for x in m.split("-") if x))


def _majuscules(mot):
    lettres = [c for c in mot if c.isalpha()]
    return len(lettres) >= 2 and all(c.isupper() for c in lettres)


def joli(mot):
    """« jean-PIERRE » -> « Jean-Pierre », « d'ARC » -> « d'Arc » ; particules en minuscules."""
    if _sans_accents(mot) in PARTICULES:
        return mot.lower()
    out = []
    for part in re.split(r"([-'’])", mot):
        out.append(part if part in "-'’" else part[:1].upper() + part[1:].lower())
    return "".join(out)


def adresse_valide(m):
    return bool(re.fullmatch(r"[^@\s<>,;\"]+@[^@\s<>,;\"]+\.[A-Za-z]{2,}", (m or "").strip()))


def _depuis_adresse(email):
    """« jean.dupont@x.fr » -> ("Jean", "Dupont") quand l'adresse a la forme prenom.nom (ou nom.prenom)."""
    local = email.split("@")[0]
    morceaux = [x for x in re.split(r"[._]", local) if x and not x.isdigit()]
    if len(morceaux) != 2 or any(len(x) < 2 or any(c.isdigit() for c in x) for x in morceaux):
        return None
    a, b = morceaux
    if est_prenom(b) and not est_prenom(a):
        a, b = b, a
    return joli(a), joli(b)


def analyser_nom(nom, email=""):
    """Nom d'affichage -> {prenom, nom_famille, sur} : « YAKITE Théodore » -> Théodore / YAKITE (sur),
    « Valentin Perat » -> Valentin / Perat (sur : prenom connu), « Weller Fiscaliste » -> rien (pas une personne
    reconnue : laisse tel quel)."""
    nom = re.sub(r"\s+", " ", (nom or "").replace('"', "").replace("'", "'").strip(" ,;"))
    if not nom or "@" in nom:
        d = _depuis_adresse(email)
        return {"prenom": d[0], "nom_famille": d[1], "sur": False} if d else None
    if "," in nom:                                    # « Dupont, Jean » (export Outlook)
        n, _v, p = nom.partition(",")
        return {"prenom": " ".join(joli(x) for x in p.split()), "nom_famille": n.strip(), "sur": True}
    mots = nom.split(" ")
    if len(mots) < 2:
        return None
    hauts = [i for i, m in enumerate(mots) if _majuscules(m)]
    if hauts and len(hauts) < len(mots):              # NOM en capitales : c'est le nom de famille
        nf = " ".join(mots[i] for i in hauts)
        pr = " ".join(joli(m) for i, m in enumerate(mots) if i not in hauts)
        return {"prenom": pr, "nom_famille": nf, "sur": True}
    if est_prenom(mots[0]) and not est_prenom(mots[-1]):
        return {"prenom": joli(mots[0]), "nom_famille": " ".join(joli(m) for m in mots[1:]), "sur": True}
    if est_prenom(mots[-1]) and not est_prenom(mots[0]):
        return {"prenom": joli(mots[-1]), "nom_famille": " ".join(joli(m) for m in mots[:-1]), "sur": True}
    d = _depuis_adresse(email)                        # l'adresse tranche : jean.dupont@ -> Jean est le prenom
    if d and _sans_accents(d[0]) in [_sans_accents(m) for m in mots]:
        p = next(m for m in mots if _sans_accents(m) == _sans_accents(d[0]))
        return {"prenom": joli(p), "nom_famille": " ".join(joli(m) for m in mots if m is not p), "sur": True}
    if est_prenom(mots[0]):                           # deux prenoms possibles : ordre habituel Prenom Nom
        return {"prenom": joli(mots[0]), "nom_famille": " ".join(joli(m) for m in mots[1:]), "sur": False}
    return None


def nom_affiche(prenom, nom_famille, ordre="prenom"):
    """Nom envoye dans les e-mails et montre dans le carnet : « Théodore Yakite » ou « YAKITE Théodore »."""
    if ordre == "nom":
        return f"{(nom_famille or '').upper()} {prenom or ''}".strip()
    return f"{prenom or ''} {joli_famille(nom_famille)}".strip()


def joli_famille(n):
    return " ".join(joli(m) for m in (n or "").split())


def cle_tri(c, tri="nom"):
    """Tri : par nom de famille (puis prenom), par prenom, ou par adresse."""
    if tri == "adresse":
        return _sans_accents(c.get("email"))
    p, n = c.get("prenom") or "", c.get("nom_famille") or ""
    if not (p or n):
        a = analyser_nom(c.get("nom") or "", c.get("email") or "")
        if a:
            p, n = a["prenom"], a["nom_famille"]
        else:
            n = c.get("nom") or c.get("email") or ""
    return (_sans_accents(p), _sans_accents(n)) if tri == "prenom" else (_sans_accents(n), _sans_accents(p))


def _n(c):
    """Nom en clair (les noms importes encodes « =?utf-8?q?...?= » sont decodes)."""
    from .courriel import _decoder
    return _decoder(c.get("nom") or "")


def nettoyer(carnet, ordre="prenom"):
    """Propositions : [{type, titre, detail, coche, ...}].
    type « fusion » (meme adresse ecrite deux fois), « nom » (nom a remettre en forme / prenom et nom reconnus),
    « meme_nom » (meme personne, plusieurs adresses : a vous de voir), « invalide » (adresse impossible)."""
    props = []
    # 1. meme adresse (majuscules, espaces) : on garde la fiche la plus complete
    groupes = {}
    for c in carnet:
        groupes.setdefault((c.get("email") or "").strip().lower(), []).append(c)
    gardes = []
    for k, g in groupes.items():
        if len(g) > 1:
            g2 = sorted(g, key=lambda c: (len(_n(c) or ""), c.get("maj") or ""), reverse=True)
            props.append({"type": "fusion", "garder": g2[0], "retirer": g2[1:], "coche": True,
                          "titre": g2[0].get("nom") or k,
                          "detail": f"{len(g)} fiches → 1 : {k}"})
        gardes.append(sorted(g, key=lambda c: (len(_n(c) or ""), c.get("maj") or ""), reverse=True)[0])
    # 2. adresses invalides
    for c in gardes:
        if not adresse_valide(c.get("email")):
            props.append({"type": "invalide", "contact": c, "coche": False, "titre": _n(c) or c.get("email"),
                          "detail": f"adresse invalide : {c.get('email')}"})
    # 3. noms : prenom / nom de famille reconnus, mise en forme
    for c in gardes:
        a = analyser_nom(_n(c) or "", c.get("email") or "")
        if not a:
            propre = re.sub(r"\s+", " ", (_n(c) or "").replace('"', "").strip())
            if propre != (_n(c) or ""):
                props.append({"type": "nom", "contact": c, "prenom": c.get("prenom", ""), "nom_famille": c.get("nom_famille", ""),
                              "nouveau": propre, "coche": True, "sur": True,
                              "titre": _n(c) or c["email"], "detail": f"« {_n(c)} » → « {propre} »"})
            continue
        nouveau = nom_affiche(a["prenom"], a["nom_famille"], ordre)
        if (nouveau != (_n(c) or "") or c.get("prenom") != a["prenom"]
                or c.get("nom_famille") != joli_famille(a["nom_famille"])):
            props.append({"type": "nom", "contact": c, "prenom": a["prenom"], "nom_famille": joli_famille(a["nom_famille"]),
                          "nouveau": nouveau, "coche": a["sur"], "sur": a["sur"], "titre": _n(c) or c["email"],
                          "inchange": nouveau == _n(c),
                          "detail": f"→ {nouveau}"})
    # 4. meme personne, plusieurs adresses (rien n'est coche : souvent une adresse perso et une pro)
    par_nom = {}
    for c in gardes:
        a = analyser_nom(_n(c) or "", c.get("email") or "")
        k = (_sans_accents(a["prenom"]), _sans_accents(a["nom_famille"])) if a else _sans_accents(_n(c))
        if k and k != ("", ""):
            par_nom.setdefault(k, []).append(c)
    for k, g in par_nom.items():
        if len(g) > 1:
            for c in g:
                props.append({"type": "meme_nom", "contact": c, "coche": False, "titre": _n(c) or c["email"],
                              "detail": c["email"]})
    return props


def appliquer(params, props):
    """Applique les propositions cochees. Les fiches retirees le sont aussi sur vos autres postes (carnet_retires) ;
    les fiches modifiees sont datees pour l'emporter a la synchronisation. Renvoie (retirees, modifiees)."""
    carnet = list(params.get("carnet") or [])
    retirer, modifs = set(), {}
    maintenant = time.strftime("%Y-%m-%dT%H:%M:%S")
    for p in props:
        if not p.get("coche"):
            continue
        if p["type"] == "fusion":
            for c in p["retirer"]:
                retirer.add(id(c))
        elif p["type"] in ("invalide", "meme_nom"):
            retirer.add(id(p["contact"]))
        elif p["type"] == "nom":
            modifs[id(p["contact"])] = p
            if p.get("edite"):
                p["nouveau"] = nom_affiche(p.get("prenom", ""), p.get("nom_famille", ""), p.get("ordre", "prenom"))
    emails_retires, out, n_mod = [], [], 0
    gardes = {(c.get("email") or "") for c in carnet if id(c) not in retirer}
    for c in carnet:
        if id(c) in retirer:
            if c.get("email") not in gardes:            # meme adresse ecrite autrement : la bonne reste
                emails_retires.append(c.get("email"))
            continue
        p = modifs.get(id(c))
        if p:
            c = dict(c, nom=p["nouveau"], maj=maintenant)
            if p.get("prenom") or p.get("nom_famille"):
                c["prenom"], c["nom_famille"] = p.get("prenom", ""), p.get("nom_famille", "")
            n_mod += 1
        out.append(c)
    params["carnet"] = out
    if emails_retires:
        params["carnet_retires"] = sorted(set(params.get("carnet_retires") or []) | set(emails_retires))
    params.enregistrer()
    return len(carnet) - len(out), n_mod
