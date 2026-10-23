"""Index de recherche de vos PDF (sur ce poste) : texte integral + date, expediteur et objet.

SQLite FTS5, sans accents ni majuscules. Mise a jour incrementale : un fichier n'est relu que si sa taille ou sa
date a change. Les PDF d'un NAS, d'un FTP ou d'un Drive sont telecharges une fois pour etre lus (puis effaces) ;
ils sont enregistres sous la forme distant:<compte>:<chemin>.
"""
import datetime, os, re, sqlite3, tempfile
import pymupdf as fitz

LIMITE_FICHIERS = 30000
TAILLE_MAX = 60 * 1024 * 1024
IGNORES = {"appdata", "$recycle.bin", "system volume information", "node_modules", ".git", ".cache", "windows",
           "program files", "program files (x86)", "@eadir", "#recycle", ".trash"}


class Index:
    def __init__(self, chemin):
        self.chemin = chemin
        self.db = sqlite3.connect(chemin, check_same_thread=False, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS docs (chemin TEXT PRIMARY KEY, nom TEXT, taille INTEGER, repere TEXT,
                pages INTEGER, date_doc TEXT, expediteur TEXT, objet TEXT, vu TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS texte USING fts5(chemin UNINDEXED, nom, contenu,
                tokenize='unicode61 remove_diacritics 2');
        """)

    def fermer(self):
        self.db.close()

    def nombre(self):
        return self.db.execute("SELECT count(*) FROM docs").fetchone()[0]

    # ---------------------------------------------------------------- ecriture
    def _connu(self, chemin, repere):
        r = self.db.execute("SELECT repere FROM docs WHERE chemin=?", (chemin,)).fetchone()
        return r is not None and r[0] == repere

    def ajouter(self, chemin, nom, taille, repere, fichier_local):
        try:
            d = fitz.open(fichier_local)
            if d.needs_pass:
                contenu, pages, meta = "", len(d), {}
            else:
                morceaux, n = [], 0
                for p in d:
                    t = p.get_text("text")
                    morceaux.append(t)
                    n += len(t)
                    if n > 300000:
                        break
                contenu, pages, meta = "\n".join(morceaux), len(d), d.metadata or {}
        except Exception:
            contenu, pages, meta = "", 0, {}
        date_doc, expediteur, objet = infos(nom, contenu, meta)
        self.db.execute("DELETE FROM texte WHERE chemin=?", (chemin,))
        self.db.execute("INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?,?,?,?)",
                        (chemin, nom, taille, repere, pages, date_doc, expediteur, objet,
                         datetime.datetime.now().isoformat(timespec="seconds")))
        self.db.execute("INSERT INTO texte (chemin, nom, contenu) VALUES (?,?,?)", (chemin, nom, contenu))

    def oublier_absents(self, prefixe, presents):
        for (c,) in self.db.execute("SELECT chemin FROM docs WHERE chemin LIKE ?", (prefixe + "%",)).fetchall():
            if c not in presents:
                self.db.execute("DELETE FROM docs WHERE chemin=?", (c,))
                self.db.execute("DELETE FROM texte WHERE chemin=?", (c,))

    def indexer_dossier(self, racine, progression=None, arret=None):
        """Parcourt un dossier de ce PC (ou un partage reseau monte). Renvoie (vus, lus)."""
        vus, lus, presents = 0, 0, set()
        for d, sous, fichiers in os.walk(racine):
            sous[:] = [x for x in sous if x.lower() not in IGNORES and not x.startswith(".")]
            for f in fichiers:
                if not f.lower().endswith(".pdf"):
                    continue
                if arret and arret():
                    self.db.commit()
                    return vus, lus
                p = os.path.join(d, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                vus += 1
                presents.add(p)
                if vus > LIMITE_FICHIERS:
                    break
                repere = f"{st.st_size}|{int(st.st_mtime)}"
                if st.st_size > TAILLE_MAX or self._connu(p, repere):
                    continue
                self.ajouter(p, f, st.st_size, repere, p)
                lus += 1
                if progression and lus % 10 == 0:
                    progression(vus, lus, p)
                    self.db.commit()
        self.oublier_absents(os.path.join(racine, ""), presents)
        self.db.commit()
        return vus, lus

    def indexer_distant(self, compte, emplacement, dossier="/", progression=None, arret=None):
        """Parcourt un NAS, un FTP ou un Drive (lister + telecharger). Renvoie (vus, lus)."""
        prefixe = f"distant:{compte['id']}:"
        vus, lus, presents = 0, 0, set()
        a_voir = [dossier or "/"]
        tmp = tempfile.mkdtemp()
        while a_voir:
            d = a_voir.pop()
            try:
                elems = emplacement.lister(d)
            except Exception:
                continue
            for e in elems:
                if arret and arret():
                    self.db.commit()
                    return vus, lus
                if e.dossier:
                    if e.nom.lower() not in IGNORES and not e.nom.startswith(".") and e.nom != "PhilPDF":
                        a_voir.append(e.chemin)
                    continue
                if not e.nom.lower().endswith(".pdf"):
                    continue
                vus += 1
                cle = prefixe + e.chemin
                presents.add(cle)
                repere = f"{e.taille}|{e.date}"
                if e.taille > TAILLE_MAX or self._connu(cle, repere):
                    continue
                local = os.path.join(tmp, "f.pdf")
                try:
                    emplacement.telecharger(e.chemin, local)
                    self.ajouter(cle, e.nom, e.taille, repere, local)
                    lus += 1
                except Exception:
                    continue
                finally:
                    try:
                        os.remove(local)
                    except OSError:
                        pass
                if progression and lus % 5 == 0:
                    progression(vus, lus, e.chemin)
                    self.db.commit()
        self.oublier_absents(prefixe, presents)
        self.db.commit()
        return vus, lus

    # ---------------------------------------------------------------- recherche
    def chercher(self, mots, expediteur="", date_debut="", date_fin="", prefixes=None, limite=200):
        """mots : liste de mots ou expressions (OU). Renvoie [{"chemin","nom","date","expediteur","objet","extrait"}]."""
        termes = []
        for m in mots or []:
            m = re.sub(r'["*^():]', " ", str(m)).strip()
            if not m:
                continue
            termes.append(f'"{m}"' if " " in m else f'"{m}"*' if len(m) >= 4 else f'"{m}"')
        conditions, valeurs = [], []
        if termes:
            conditions.append("texte MATCH ?")
            valeurs.append(" OR ".join(termes))
        if expediteur:
            conditions.append("(docs.expediteur LIKE ? OR docs.nom LIKE ? OR docs.chemin IN "
                              "(SELECT chemin FROM texte WHERE texte MATCH ?))")
            valeurs += [f"%{expediteur}%", f"%{expediteur}%", '"' + re.sub(r'["*^():]', " ", expediteur).strip() + '"']
        if date_debut:
            conditions.append("docs.date_doc >= ?")
            valeurs.append(date_debut)
        if date_fin:
            conditions.append("docs.date_doc <= ?")
            valeurs.append(date_fin)
        if prefixes:
            conditions.append("(" + " OR ".join("docs.chemin LIKE ?" for _p in prefixes) + ")")
            valeurs += [p + "%" for p in prefixes]
        where = " AND ".join(conditions) or "1"
        ordre = "bm25(texte)" if termes else "docs.date_doc DESC"
        extrait = "snippet(texte, 2, '[', ']', ' … ', 14)" if termes else "substr(texte.contenu, 1, 160)"
        sql = (f"SELECT docs.chemin, docs.nom, docs.date_doc, docs.expediteur, docs.objet, {extrait} "
               f"FROM texte JOIN docs ON docs.chemin = texte.chemin WHERE {where} ORDER BY {ordre} LIMIT ?")
        try:
            lignes = self.db.execute(sql, valeurs + [limite]).fetchall()
        except sqlite3.OperationalError:
            return []
        return [{"chemin": c, "nom": n, "date": dt, "expediteur": ex, "objet": ob,
                 "extrait": re.sub(r"\s+", " ", ext or "").strip()} for c, n, dt, ex, ob, ext in lignes]


# ------------------------------------------------------------------ date, expediteur, objet
_MOIS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
         "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12}


def _date_texte(t):
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2}|19\d{2})\b", t)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(_MOIS) + r")\s+(20\d{2}|19\d{2})\b", t, re.I)
    if m:
        try:
            return datetime.date(int(m.group(3)), _MOIS[m.group(2).lower()], int(m.group(1))).isoformat()
        except ValueError:
            pass
    return ""


def infos(nom, contenu, meta):
    """(date AAAA-MM-JJ, expediteur, objet) : nom donne par « Renommer et classer », sinon le texte, sinon le PDF."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})\s+(.+?)(?:\s+[–-]\s+(.+?))?\.pdf$", nom, re.I)
    if m:
        return m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
    date = _date_texte(contenu[:3000])
    if not date:
        c = (meta or {}).get("creationDate") or ""
        m = re.match(r"D:(\d{4})(\d{2})(\d{2})", c)
        if m:
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return date, "", ""
