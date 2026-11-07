"""Aide TWAIN 32 bits de PhilPDF (Windows).

PhilPDF est un programme 64 bits : il ne parle qu'aux pilotes TWAIN 64 bits. Certains scanners n'ont un pilote
fiable qu'en 32 bits : c'est le cas des scanners reseau relies par un « pont » du fabricant (Avision : Virtual
Scanner Link, que le logiciel Avision Capture Tool, 32 bits, utilise). Ce petit programme 32 bits, livre a cote de
PhilPDF, fait la numerisation a sa place et lui rend les pages en fichiers.

Il ne depend que de Python et de pytwain. Il n'affiche rien lui-meme (hors la fenetre du pilote si on la demande).
Commandes :
  aide_twain32.exe liste
  aide_twain32.exe numeriser <dossier> <nom de la source> <mode> <dpi> <source> <interface 0|1>
Il ecrit sur sa sortie une ligne JSON par evenement :
  {"gestionnaire": "..."}  {"sources": [...]}  {"page": "chemin.bmp"}
  {"fin": n}  {"erreur": "...", "etapes": [...], "ouverture": true|false}
"""
import ctypes
import json
import logging
import os
import sys
import traceback


def dire(**k):
    sys.stdout.write(json.dumps(k, ensure_ascii=False) + "\n")
    sys.stdout.flush()


ETAPES = []


class _Suivi(logging.Handler):
    def emit(self, r):
        ETAPES.append(r.getMessage())
        del ETAPES[:-12]


def _fenetre():
    """Fenetre cachee de ce programme : le pilote y envoie ses messages (la boucle de pytwain les lit)."""
    u = ctypes.windll.user32
    u.CreateWindowExW.restype = ctypes.c_void_p
    h = u.CreateWindowExW(0, "STATIC", "PhilPDF TWAIN 32", 0, 0, 0, 0, 0, None, None, None, None)
    return int(h or 0)


def _gestionnaires():
    w = os.environ.get("WINDIR", r"C:\Windows")
    # TWAINDSM 32 bits (pilotes recents), puis l'ancien twain_32.dll de Windows (pilotes anciens, Avision Capture Tool)
    return [(os.path.join(w, "SysWOW64", "TWAINDSM.dll"), 2), ("twaindsm.dll", 2), (os.path.join(w, "twain_32.dll"), 1)]


def _ouvrir(hwnd, voulu=None):
    import twain
    erreurs = []
    for nom, proto in _gestionnaires():
        if voulu and nom != voulu:
            continue
        if os.path.isabs(nom) and not os.path.exists(nom):
            continue
        try:
            sm = twain.SourceManager(hwnd, dsm_name=nom, ProtocolMajor=proto, ProductName="PhilPDF",
                                     Manufacturer="PhilPDF", ProductFamily="PhilPDF")
            return sm, nom
        except Exception as e:                          # noqa: BLE001
            erreurs.append(f"{nom} : {e}")
    raise RuntimeError("; ".join(erreurs) or "aucun gestionnaire TWAIN 32 bits")


def liste():
    hwnd = _fenetre()
    vus, out = set(), []
    for nom, _p in _gestionnaires():
        try:
            sm, n = _ouvrir(hwnd, nom)
        except Exception as e:                          # noqa: BLE001
            dire(journal=f"{nom} : {e}")
            continue
        try:
            for s in sm.source_list:
                if s not in vus:
                    vus.add(s)
                    out.append({"nom": s, "gestionnaire": n})
        except Exception as e:                          # noqa: BLE001
            dire(journal=f"{n} : liste illisible : {e}")
        try:
            sm.close()
        except Exception:                               # noqa: BLE001
            pass
    dire(sources=out)


def numeriser(dossier, nom, mode, dpi, source, interface, gestionnaire=None):
    import twain
    from twain.lowlevel import constants as C
    lg = logging.getLogger("twain")
    lg.addHandler(_Suivi())
    lg.setLevel(logging.INFO)
    hwnd = _fenetre()
    sm, g = _ouvrir(hwnd, gestionnaire or None)
    dire(gestionnaire=g)
    pages = []
    src = sm.open_source(nom)
    if src is None:
        dire(fin=0)
        return
    try:
        def cap(c, t, v):
            try:
                src.set_capability(c, t, v)
            except Exception as e:                      # noqa: BLE001
                dire(journal=f"réglage {c} refusé ({e})")
        cap(C.ICAP_PIXELTYPE, C.TWTY_UINT16, {"couleur": C.TWPT_RGB, "auto": C.TWPT_RGB, "gris": C.TWPT_GRAY,
                                             "nb": C.TWPT_GRAY}[mode])
        cap(C.ICAP_UNITS, C.TWTY_UINT16, C.TWUN_INCHES)
        cap(C.ICAP_XRESOLUTION, C.TWTY_FIX32, float(dpi))
        cap(C.ICAP_YRESOLUTION, C.TWTY_FIX32, float(dpi))
        cap(C.CAP_FEEDERENABLED, C.TWTY_BOOL, source != "vitre")
        if source != "vitre":
            cap(C.CAP_AUTOFEED, C.TWTY_BOOL, True)
            cap(C.CAP_XFERCOUNT, C.TWTY_INT16, -1)
        cap(C.CAP_DUPLEXENABLED, C.TWTY_BOOL, source == "recto_verso")
        par_fichier = True
        try:
            _o, (_o2, _o3, mecas) = src.get_capability(C.ICAP_XFERMECH)
            par_fichier = C.TWSX_FILE in mecas
        except Exception as e:                          # noqa: BLE001
            dire(journal=f"modes de transfert illisibles ({e}) : essai par fichier")
        dire(journal=f"transfert {'par fichier' if par_fichier else 'natif (mémoire)'}, "
                     f"fenêtre du pilote {'oui' if interface else 'non'}")
        if par_fichier:
            def avant(_info):
                f = os.path.join(dossier, f"p{len(pages):03d}.bmp")
                pages.append(f)
                return f

            def apres(_reste):
                dire(page=pages[-1])
                if source == "vitre":
                    raise twain.exceptions.CancelAll
            try:
                src.acquire_file(before=avant, after=apres, show_ui=interface, modal=interface)
            except (twain.exceptions.DSTransferCancelled, twain.exceptions.CancelAll):
                pass
        else:
            def apres_natif(img, _reste):
                f = os.path.join(dossier, f"p{len(pages):03d}.bmp")
                img.save(f)
                pages.append(f)
                dire(page=f)
                if source == "vitre":
                    raise twain.exceptions.CancelAll
            try:
                src.acquire_natively(after=apres_natif, show_ui=interface, modal=interface)
            except (twain.exceptions.DSTransferCancelled, twain.exceptions.CancelAll):
                pass
    finally:
        try:
            src.close()
        except Exception:                               # noqa: BLE001
            pass
        try:
            sm.close()
        except Exception:                               # noqa: BLE001
            pass
    dire(fin=len(pages))


def main(a):
    try:
        if a[:1] == ["liste"]:
            liste()
        elif a[:1] == ["numeriser"] and len(a) >= 7:
            numeriser(a[1], a[2], a[3], int(a[4]), a[5], a[6] == "1", a[7] if len(a) > 7 else None)
        else:
            dire(erreur="commande inconnue : " + " ".join(a))
            return 2
    except Exception as e:                              # noqa: BLE001
        pile = [f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in traceback.extract_tb(e.__traceback__)[-4:]]
        ouverture = any("MSG_OPENDS" in x for x in ETAPES[-3:]) and not any("MSG_ENABLEDS" in x for x in ETAPES)
        dire(erreur=f"{type(e).__name__} : {e}", etapes=ETAPES[-6:], endroit=pile, ouverture=ouverture)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
