"""Journal des echanges (Drives, NAS, FTP, IA, autorisations) garde dans un fichier, pour retrouver ce qui
s'est passe apres coup. Mots de passe, codes et jetons masques. Taille limitee : le plus ancien est jete."""
import os, threading, time

TAILLE_MAX = 2 * 1024 * 1024
_verrou = threading.Lock()


def chemin():
    from .config import dossier_donnees
    d = os.path.join(dossier_donnees(), "journaux")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "echanges.log")


def ecrire(source, texte):
    """Ajoute une ligne : date, origine (Google Drive, NAS..., IA), texte masque."""
    try:
        from .distant import masquer
        ligne = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  [{source}]  {masquer(str(texte))}\n"
        with _verrou:
            p = chemin()
            if os.path.exists(p) and os.path.getsize(p) > TAILLE_MAX:
                ancien = p + ".1"
                if os.path.exists(ancien):
                    os.remove(ancien)
                os.replace(p, ancien)
            with open(p, "a", encoding="utf-8") as f:
                f.write(ligne)
    except Exception:
        pass                                       # le journal ne doit jamais faire echouer une operation


def noter_version(version):
    """Au demarrage : note la version lancee et, si elle a change depuis la fois precedente, la mise a jour faite."""
    try:
        f = os.path.join(os.path.dirname(chemin()), "derniere_version.txt")
        avant = open(f, encoding="utf-8").read().strip() if os.path.exists(f) else ""
        if avant and avant != version:
            ecrire("mise a jour", f"PhilPDF {avant} -> {version} : mise a jour faite, nouvelle version lancee")
        elif not avant:
            ecrire("mise a jour", f"PhilPDF {version} lance (premiere fois sur ce poste)")
        with open(f, "w", encoding="utf-8") as g:
            g.write(version)
    except Exception:
        pass
