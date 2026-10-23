"""Comparaison de deux versions d'un PDF, sans IA : mot a mot, resultat cote a cote.

comparer(a, b) -> liste de changements ; rapport(a, b, changements, sortie, explication=None) fabrique un PDF :
une page de synthese (et l'explication de l'IA si elle est fournie), puis chaque page de l'ancienne version a
gauche et de la nouvelle a droite, retraits surlignes en rouge, ajouts en vert, modifications en orange.
"""
import difflib, re
import pymupdf as fitz

ROUGE, VERT, ORANGE = (0.90, 0.22, 0.21), (0.18, 0.66, 0.30), (0.95, 0.60, 0.07)


def mots(doc):
    """[(texte, page, Rect)] dans l'ordre de lecture."""
    out = []
    for i, p in enumerate(doc):
        for x0, y0, x1, y1, t, b, l, n in sorted(p.get_text("words"), key=lambda w: (w[5], w[6], w[7])):
            out.append((t, i, fitz.Rect(x0, y0, x1, y1)))
    return out


def _norm(t):
    return re.sub(r"[’']", "'", t.lower().strip(".,;:!?()«»\"“”"))


def comparer(doc_a, doc_b):
    """[{"genre": "retrait|ajout|modif", "avant": str, "apres": str, "mots_a": [...], "mots_b": [...],
    "page_a": n, "page_b": n, "contexte": str}]"""
    ma, mb = mots(doc_a), mots(doc_b)
    sm = difflib.SequenceMatcher(None, [_norm(m[0]) for m in ma], [_norm(m[0]) for m in mb], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        genre = {"delete": "retrait", "insert": "ajout", "replace": "modif"}[op]
        ref, k1, k2 = (mb, j1, j2) if op == "insert" else (ma, i1, i2)
        ctx_avant = " ".join(m[0] for m in ref[max(0, k1 - 8):k1])
        ctx_apres = " ".join(m[0] for m in ref[k2:k2 + 8])
        out.append({"genre": genre, "avant": " ".join(m[0] for m in ma[i1:i2]), "apres": " ".join(m[0] for m in mb[j1:j2]),
                    "mots_a": ma[i1:i2], "mots_b": mb[j1:j2],
                    "page_a": (ma[i1][1] if i1 < i2 else (ma[i1 - 1][1] if i1 else 0)) + 1,
                    "page_b": (mb[j1][1] if j1 < j2 else (mb[j1 - 1][1] if j1 else 0)) + 1,
                    "contexte": f"… {ctx_avant} [[{' '.join(m[0] for m in ref[k1:k2])}]] {ctx_apres} …"})
    return out


def texte_pour_ia(changements, max_car=60000):
    lignes = []
    for i, c in enumerate(changements, 1):
        if c["genre"] == "retrait":
            l = f"{i}. RETIRÉ (p. {c['page_a']}) : « {c['avant']} » — contexte : {c['contexte']}"
        elif c["genre"] == "ajout":
            l = f"{i}. AJOUTÉ (p. {c['page_b']}) : « {c['apres']} » — après : {c['contexte']}"
        else:
            l = f"{i}. MODIFIÉ (p. {c['page_a']}→{c['page_b']}) : « {c['avant']} » devient « {c['apres']} » — contexte : {c['contexte']}"
        lignes.append(l)
        if sum(len(x) for x in lignes) > max_car:
            lignes.append("[... autres différences non transmises ...]")
            break
    return "\n".join(lignes)


def pages_html(html, css="* {font-family: sans-serif; font-size: 10.5pt} h2 {font-size: 17pt} h3 {font-size: 13pt}"):
    """PDF A4 (autant de pages qu'il faut) a partir d'un petit HTML."""
    import io
    tampon = io.BytesIO()
    story = fitz.Story(html, user_css=css)
    w = fitz.DocumentWriter(tampon)
    zone = fitz.Rect(48, 48, 547, 794)
    plus = True
    while plus:
        dev = w.begin_page(fitz.paper_rect("a4"))
        plus, _r = story.place(zone)
        story.draw(dev)
        w.end_page()
    w.close()
    return fitz.open("pdf", tampon.getvalue())


def _surligner(page, rects, dx, couleur):
    for r in rects:
        q = fitz.Rect(r.x0 + dx - 1, r.y0 - 1, r.x1 + dx + 1, r.y1 + 1)
        page.draw_rect(q, color=None, fill=couleur, fill_opacity=0.32, overlay=True)


def rapport(doc_a, doc_b, changements, sortie, nom_a="A", nom_b="B", explication=None, titres=None):
    """PDF de comparaison : synthese (+ explication), puis pages cote a cote."""
    titres = titres or {}
    out = fitz.open()
    n_ret = sum(1 for c in changements if c["genre"] == "retrait")
    n_aj = sum(1 for c in changements if c["genre"] == "ajout")
    n_mod = sum(1 for c in changements if c["genre"] == "modif")
    html = [f"<h2>{titres.get('titre', 'Comparaison')}</h2>",
            f"<p><b>{titres.get('ancienne', 'Ancienne version')} :</b> {nom_a}<br><b>{titres.get('nouvelle', 'Nouvelle version')} :</b> {nom_b}</p>",
            f"<p>{titres.get('bilan', '{m} modification(s), {a} ajout(s), {r} retrait(s)').format(m=n_mod, a=n_aj, r=n_ret)}</p>"]
    if not changements:
        html.append(f"<p><b>{titres.get('identiques', 'Le texte des deux versions est identique.')}</b></p>")
    if explication:
        html.append(f"<h3>{titres.get('explication', 'Explication')}</h3>")
        html.append(explication)
    html.append(f"<p style='color:#777;font-size:9px'>{titres.get('legende', '')}</p>")
    out.insert_pdf(pages_html("".join(html)))
    par_page_a, par_page_b = {}, {}
    for c in changements:
        coul = {"retrait": ROUGE, "ajout": VERT, "modif": ORANGE}[c["genre"]]
        for t, pg, r in c["mots_a"]:
            par_page_a.setdefault(pg, []).append((r, coul))
        for t, pg, r in c["mots_b"]:
            par_page_b.setdefault(pg, []).append((r, coul))
    for i in range(max(len(doc_a), len(doc_b))):
        wa = doc_a[i].rect.width if i < len(doc_a) else 0
        ha = doc_a[i].rect.height if i < len(doc_a) else 0
        wb = doc_b[i].rect.width if i < len(doc_b) else 0
        hb = doc_b[i].rect.height if i < len(doc_b) else 0
        marge = 24
        p = out.new_page(width=wa + wb + marge, height=max(ha, hb) + 22)
        if i < len(doc_a):
            p.show_pdf_page(fitz.Rect(0, 22, wa, 22 + ha), doc_a, i)
            p.insert_text((6, 15), f"{titres.get('ancienne', 'Ancienne version')} - p. {i + 1}", fontsize=9, color=(0.4, 0.4, 0.4))
        if i < len(doc_b):
            p.show_pdf_page(fitz.Rect(wa + marge, 22, wa + marge + wb, 22 + hb), doc_b, i)
            p.insert_text((wa + marge + 6, 15), f"{titres.get('nouvelle', 'Nouvelle version')} - p. {i + 1}", fontsize=9, color=(0.4, 0.4, 0.4))
        p.draw_line((wa + marge / 2, 0), (wa + marge / 2, p.rect.height), color=(0.75, 0.75, 0.75), width=0.8)
        for r, coul in par_page_a.get(i, []):
            _surligner(p, [r + (0, 22, 0, 22)], 0, coul)
        for r, coul in par_page_b.get(i, []):
            _surligner(p, [r + (0, 22, 0, 22)], wa + marge, coul)
    out.set_metadata({"producer": "PhilPDF", "title": titres.get("titre", "Comparaison")})
    out.save(sortie, garbage=3, deflate=True)
    return n_mod, n_aj, n_ret
