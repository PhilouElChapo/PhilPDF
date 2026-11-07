"""PhilPDF - numerisation depuis un scanner.

Windows : WIA (Windows Image Acquisition), present sur tous les Windows, aucun pilote
          supplementaire a part celui du scanner. Chargeur, recto-verso et vitre.
Linux   : SANE (commande scanimage).

Modes (reprend la maquette validee) :
  auto     : couleur numerisee puis texte en noir et blanc net, photos gardees ;
  nb       : noir et blanc (courriers, factures), le plus leger ;
  gris     : niveaux de gris (tampons, signatures, documents pales) ;
  couleur  : photos, plans.
"""
import io, os, shutil, subprocess, sys, tempfile
import numpy as np
import pymupdf as fitz
from app.langue import _

# taille estimee par page A4, en Ko, selon mode et resolution (mesuree sur de vrais scans)
ESTIMATION = {"auto": 100, "nb": 60, "gris": 200, "couleur": 400}
DPI_CONSEILLE = {"auto": 300, "nb": 300, "gris": 200, "couleur": 200}


def estimer_ko(mode, dpi, pages=1):
    base = ESTIMATION[mode] * (dpi / DPI_CONSEILLE[mode]) ** 2
    return int(base * pages)


# ------------------------------------------------------------------ Windows (WIA)
WIA_INTENT = {"couleur": 1, "auto": 1, "gris": 2, "nb": 4}
FORMAT_PNG = "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}"


def _journal(t):
    try:
        from app.journal import ecrire
        ecrire("scanner", t)
    except Exception:                                   # noqa: BLE001
        pass


def scanners_wia():
    """[(identifiant, nom)] des scanners WIA de Windows. Un appareil illisible (debranche, fax, sans nom) est laisse
    de cote SANS cacher les autres ; tout est note dans le journal."""
    out = []
    try:
        import pythoncom
        pythoncom.CoInitialize()                        # appel possible hors du fil principal
    except Exception:                                   # noqa: BLE001
        pass
    try:
        import win32com.client
        dm = win32com.client.Dispatch("WIA.DeviceManager")
        n = dm.DeviceInfos.Count
    except Exception as e:                              # noqa: BLE001
        _journal(f"WIA indisponible : {e}")
        return out
    for i in range(1, n + 1):
        try:
            info = dm.DeviceInfos.Item(i)
            typ, ident = info.Type, info.DeviceID
            nom = None
            for p in ("Name", "Description", "Manufacturer"):
                try:
                    nom = info.Properties(p).Value
                    if nom:
                        break
                except Exception:                       # noqa: BLE001
                    continue
            _journal(f"WIA appareil {i}/{n} : type {typ}, {nom or ident}")
            if typ == 1:                                # 1 scanner, 2 appareil photo, 3 video
                out.append((ident, nom or ident))
        except Exception as e:                          # noqa: BLE001
            _journal(f"WIA appareil {i}/{n} illisible : {e}")
    return out


def scanners_reseau():
    """[("escl:<adresse>", nom)] des scanners reseau sans pilote (eSCL / AirScan)."""
    try:
        from . import escl
        l = escl.chercher()
        _journal(f"réseau (eSCL) : {len(l)} scanner(s) " + ", ".join(f"{n} ({u})" for u, n in l))
        return [("escl:" + u, n + " " + _("(réseau, sans pilote)")) for u, n in l]
    except Exception as e:                              # noqa: BLE001
        _journal(f"recherche réseau (eSCL) impossible : {e}")
        return []


# ------------------------------------------------------------------ Windows (TWAIN)
# Beaucoup de scanners USB (Avision, Fujitsu, Plustek...) n'ont qu'un pilote TWAIN, sans WIA : la fenetre de Windows
# ne les voit pas, les logiciels de numerisation passent par TWAIN. PhilPDF est un programme 64 bits : il lui faut le
# gestionnaire TWAIN 64 bits (TWAINDSM.dll, installe par les pilotes recents) et un pilote 64 bits du scanner.
_SM = None            # gestionnaire TWAIN : ouvert UNE fois pour toute la session (le rouvrir apres l'avoir ferme
_SM_ERREUR = None    # fait planter certains pilotes : « access violation », puis « ConditionCode = 0 »)


def _dsm(fenetre=None):
    """Le gestionnaire TWAIN de la session, ouvert avec la fenetre de PhilPDF (les pilotes y attachent leurs
    fenetres et leurs messages). Une premiere ouverture ratee n'est pas retentee (elle laisse le pilote instable)."""
    global _SM, _SM_ERREUR
    if _SM is not None:
        if fenetre and not _SM._hwnd:
            _SM._hwnd = int(fenetre)
        return _SM
    if _SM_ERREUR:
        raise RuntimeError(_SM_ERREUR)
    import twain
    erreurs = []
    for nom in (None, os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "TWAINDSM.dll")):
        try:
            _SM = twain.SourceManager(int(fenetre) if fenetre else None, dsm_name=nom, ProductName="PhilPDF",
                                      Manufacturer="PhilPDF", ProductFamily="PhilPDF")
            _journal(f"TWAIN : gestionnaire ouvert ({nom or 'twaindsm.dll'}, fenêtre {'oui' if fenetre else 'non'})")
            return _SM
        except Exception as e:                          # noqa: BLE001
            erreurs.append(f"{nom or 'twaindsm.dll'} : {e}")
    _SM_ERREUR = "; ".join(erreurs)
    raise RuntimeError(_SM_ERREUR)


def scanners_twain(fenetre=None):
    """[("twain:<nom>", nom)] des sources TWAIN (Windows). fenetre : identifiant (HWND) de la fenetre de PhilPDF."""
    if sys.platform != "win32":
        return []
    try:
        sm = _dsm(fenetre)
    except ImportError:
        _journal("TWAIN : module absent de ce paquet")
        return []
    except Exception as e:                              # noqa: BLE001
        _journal(f"TWAIN 64 bits indisponible (gestionnaire TWAINDSM.dll absent ?) : {e}")
        return []
    try:
        noms = list(sm.source_list)
    except Exception as e:                              # noqa: BLE001
        _journal(f"TWAIN : liste des sources illisible : {e}")
        noms = []
    _journal(f"TWAIN : {len(noms)} source(s) " + ", ".join(noms) + ("" if noms else
             " (un pilote 32 bits seulement n'est pas visible d'un programme 64 bits)"))
    return [("twain:" + n, n + " " + _("(TWAIN)")) for n in noms]


class OuvertureImpossible(RuntimeError):
    """Le pilote TWAIN plante des l'ouverture de la source : scanner eteint, debranche, ou scanner reseau pas encore
    relie (Avision : Virtual Scanner Link). Reessayer avec la fenetre du pilote n'y change rien."""


def _numeriser_twain(nom, mode, dpi, source, fenetre=None, interface=False):
    """Images (octets BMP) numerisees par la source TWAIN « nom ». interface : la fenetre du pilote du scanner.
    Transfert PAR FICHIER d'abord (le pilote ecrit chaque page dans un BMP : aucune memoire du pilote a lire, le plus
    sur en 64 bits) ; transfert « natif » (image en memoire) seulement si le pilote ne sait pas ecrire de fichier.
    Les dernieres etapes TWAIN et l'endroit d'un plantage sont notes au journal."""
    import logging
    import traceback
    import twain
    from twain.lowlevel import constants as C
    etapes = []

    class _Suivi(logging.Handler):
        def emit(self, r):
            etapes.append(r.getMessage())
            del etapes[:-12]
    lg = logging.getLogger("twain")
    suivi = _Suivi()
    lg.addHandler(suivi)
    niveau = lg.level
    lg.setLevel(logging.INFO)
    sm = _dsm(fenetre)                                  # le meme gestionnaire que pour la liste (jamais rouvert)
    images = []
    try:
        src = sm.open_source(nom)
        if src is None:
            return []
        try:
            def cap(c, t, v):
                try:
                    src.set_capability(c, t, v)
                except Exception as e:                  # noqa: BLE001
                    _journal(f"TWAIN {nom} : réglage {c} refusé ({e})")
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
            dossier = tempfile.mkdtemp(prefix="philpdf_twain_")
            par_fichier = True
            try:
                _o, (_o2, _o3, mecas) = src.get_capability(C.ICAP_XFERMECH)
                par_fichier = C.TWSX_FILE in mecas
            except Exception as e:                      # noqa: BLE001
                _journal(f"TWAIN {nom} : modes de transfert illisibles ({e}) : essai par fichier")
            _journal(f"TWAIN {nom} : transfert {'par fichier' if par_fichier else 'natif (mémoire)'}, "
                     f"fenêtre du pilote {'oui' if interface else 'non'}")
            if par_fichier:
                chemins = []

                def avant(_info):
                    f = os.path.join(dossier, f"p{len(chemins):03d}.bmp")
                    chemins.append(f)
                    return f

                def apres_fichier(_reste):
                    with open(chemins[-1], "rb") as fh:
                        images.append(fh.read())
                    if source == "vitre":
                        raise twain.exceptions.CancelAll
                try:
                    src.acquire_file(before=avant, after=apres_fichier, show_ui=interface, modal=interface)
                except (twain.exceptions.DSTransferCancelled, twain.exceptions.CancelAll):
                    pass
            else:
                def apres(img, reste):
                    f = os.path.join(dossier, f"p{len(images):03d}.bmp")
                    img.save(f)                         # la memoire de l'image est rendue par pytwain (une seule fois)
                    with open(f, "rb") as fh:
                        images.append(fh.read())
                    if source == "vitre":
                        raise twain.exceptions.CancelAll
                try:
                    src.acquire_natively(after=apres, show_ui=interface, modal=interface)
                except (twain.exceptions.DSTransferCancelled, twain.exceptions.CancelAll):
                    pass
        finally:
            try:
                src.close()                             # la source se ferme ; le gestionnaire reste ouvert
            except Exception as e:                      # noqa: BLE001
                _journal(f"TWAIN {nom} : fermeture de la source : {e}")
    except Exception as e:
        pile = [f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in traceback.extract_tb(e.__traceback__)[-4:]]
        _journal(f"TWAIN {nom} : {type(e).__name__} : {e}")
        _journal(f"TWAIN {nom} : dernières étapes : " + " > ".join(etapes[-6:] or ["aucune"]))
        _journal(f"TWAIN {nom} : endroit : " + " > ".join(pile))
        if any("MSG_OPENDS" in x for x in etapes[-3:]) and not any("MSG_ENABLEDS" in x or "MSG_ENALEDS" in x for x in etapes):
            raise OuvertureImpossible(_(
                "Le scanner « {n} » n'a pas pu être ouvert : son pilote s'est arrêté dès l'ouverture, avant de "
                "numériser.\n\n• Vérifiez qu'il est allumé et branché.\n• Scanner en Wi-Fi ou réseau : reliez-le "
                "d'abord avec l'outil du fabricant (Avision : « Virtual Scanner Link », sélectionnez le scanner puis "
                "reliez-le), puis réessayez.\n• Sinon, branchez-le en USB.", n=nom)) from e
        raise
    finally:
        lg.removeHandler(suivi)
        lg.setLevel(niveau)
    _journal(f"TWAIN {nom} : {len(images)} page(s)")
    return images


# ------------------------------------------------------------------ Windows (TWAIN 32 bits, par l'aide)
# Certains pilotes ne marchent qu'en 32 bits : scanners reseau relies par le « pont » du fabricant (Avision : Virtual
# Scanner Link), anciens pilotes. Un petit programme 32 bits livre avec PhilPDF (twain32\aide_twain32.exe) numerise a
# sa place et rend les pages en fichiers. Rien d'autre n'est installe sur le poste.
_SOURCES32 = None      # {nom: gestionnaire} lues une fois par session
_PREFERER32 = None    # sources dont le pilote 64 bits a plante a l'ouverture : 32 bits directement (retenu d'une
                      # session a l'autre : le plantage 64 bits n'est jamais rejoue)


def _fichier_preferer32():
    try:
        from app.config import dossier_donnees
        return os.path.join(dossier_donnees(), "twain32.json")
    except Exception:                                   # noqa: BLE001
        return None


def preferer32():
    """Ensemble des sources a numeriser directement en 32 bits (lu une fois, puis tenu a jour)."""
    global _PREFERER32
    if _PREFERER32 is None:
        _PREFERER32 = set()
        f = _fichier_preferer32()
        try:
            if f and os.path.exists(f):
                import json
                with open(f, encoding="utf-8") as fh:
                    _PREFERER32 = set(json.load(fh).get("sources", []))
        except Exception as e:                          # noqa: BLE001
            _journal(f"TWAIN 32 bits : préférences illisibles ({e})")
    return _PREFERER32


def _retenir32(nom):
    preferer32().add(nom)
    f = _fichier_preferer32()
    if not f:
        return
    try:
        import json
        with open(f, "w", encoding="utf-8") as fh:
            json.dump({"sources": sorted(_PREFERER32)}, fh, ensure_ascii=False, indent=1)
        _journal(f"TWAIN {nom} : retenu, les prochaines fois directement par le pilote 32 bits ({f})")
    except Exception as e:                              # noqa: BLE001
        _journal(f"TWAIN 32 bits : préférence non enregistrée ({e})")


def aide32():
    """Chemin de l'aide TWAIN 32 bits, ou None (pas sous Windows, ou absente du paquet)."""
    if sys.platform != "win32":
        return None
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else \
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "PhilPDF")
    f = os.path.join(base, "twain32", "aide_twain32.exe")
    return f if os.path.exists(f) else None


def _lancer32(args, attente=None, delai=None):
    """Lance l'aide 32 bits ; rend la liste de ses messages (dicts). attente() est appelee pendant qu'elle travaille
    (la fenetre de progression de PhilPDF reste vivante)."""
    import json
    import time
    f = aide32()
    if not f:
        raise RuntimeError(_("L'aide TWAIN 32 bits est absente de ce paquet de PhilPDF."))
    sortie = tempfile.NamedTemporaryFile(prefix="philpdf_t32_", suffix=".txt", delete=False)
    sortie.close()
    with open(sortie.name, "w") as out:
        p = subprocess.Popen(([sys.executable] if f.endswith(".py") else []) + [f] + args, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        debut = time.time()
        while p.poll() is None:
            if attente:
                attente()
            time.sleep(0.05)
            if delai and time.time() - debut > delai:
                p.kill()
                raise RuntimeError(_("L'aide TWAIN 32 bits ne répond plus (plus de {n} s).", n=int(delai)))
    msgs = []
    with open(sortie.name, encoding="utf-8", errors="replace") as fh:
        for l in fh:
            try:
                msgs.append(json.loads(l))
            except ValueError:
                if l.strip():
                    msgs.append({"journal": l.strip()})
    try:
        os.remove(sortie.name)
    except OSError:
        pass
    for m in msgs:
        if "journal" in m:
            _journal("TWAIN 32 bits : " + str(m["journal"]))
    if p.returncode not in (0, 1, 2) and not any("erreur" in m or "fin" in m or "sources" in m for m in msgs):
        msgs.append({"erreur": f"l'aide s'est arrêtée (code {p.returncode})", "etapes": [], "ouverture": False})
    return msgs


def scanners_twain32():
    """{nom: gestionnaire} des sources TWAIN 32 bits (vide si l'aide est absente)."""
    global _SOURCES32
    if _SOURCES32:                                       # une liste vide est relue (pont relie entre-temps)
        return _SOURCES32
    _SOURCES32 = {}
    if not aide32():
        return _SOURCES32
    try:
        for m in _lancer32(["liste"], delai=30):
            for s in m.get("sources", []):
                _SOURCES32.setdefault(s["nom"], s["gestionnaire"])
        _journal(f"TWAIN 32 bits : {len(_SOURCES32)} source(s) " + ", ".join(_SOURCES32))
    except Exception as e:                              # noqa: BLE001
        _journal(f"TWAIN 32 bits : liste impossible : {e}")
    return _SOURCES32


def _attente_qt():
    try:
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
    except Exception:                                   # noqa: BLE001
        pass


def _numeriser_twain32(nom, mode, dpi, source, interface=False):
    """Pages (octets BMP) numerisees par l'aide 32 bits."""
    dossier = tempfile.mkdtemp(prefix="philpdf_twain32_")
    g = scanners_twain32().get(nom, "")
    _journal(f"TWAIN 32 bits {nom} : numérisation ({g or 'gestionnaire automatique'}, fenêtre du pilote "
             f"{'oui' if interface else 'non'})")
    msgs = _lancer32(["numeriser", dossier, nom, mode, str(dpi), source, "1" if interface else "0"] + ([g] if g else []),
                     attente=_attente_qt)
    images = []
    for m in msgs:
        if "page" in m and os.path.exists(m["page"]):
            with open(m["page"], "rb") as fh:
                images.append(fh.read())
    err = next((m for m in msgs if "erreur" in m), None)
    if err and not images:
        _journal(f"TWAIN 32 bits {nom} : {err['erreur']}")
        _journal(f"TWAIN 32 bits {nom} : dernières étapes : " + " > ".join(err.get("etapes") or ["aucune"]))
        if err.get("endroit"):
            _journal(f"TWAIN 32 bits {nom} : endroit : " + " > ".join(err["endroit"]))
        if err.get("ouverture"):
            raise OuvertureImpossible(_(
                "Le scanner « {n} » n'a pas pu être ouvert, ni par son pilote 64 bits ni par son pilote 32 bits.\n\n"
                "• Vérifiez qu'il est allumé et branché.\n• Scanner en Wi-Fi ou réseau : vérifiez qu'il est bien relié "
                "dans l'outil du fabricant (Avision : « Virtual Scanner Link ») et qu'aucun autre poste ne l'utilise.\n"
                "• Sinon, branchez-le en USB.", n=nom))
        raise RuntimeError(_("Pilote TWAIN 32 bits : {e}", e=err["erreur"]))
    _journal(f"TWAIN 32 bits {nom} : {len(images)} page(s)")
    return images


def scanners(reseau=True, fenetre=None):
    """[(identifiant, nom)] des scanners disponibles : WIA (Windows) ou SANE (Linux), puis ceux du reseau (eSCL)."""
    out = []
    if sys.platform == "win32":
        out = scanners_wia()
        noms = {n for _i, n in out}
        tw = [(i, n) for i, n in scanners_twain(fenetre) if n.rsplit(" (", 1)[0] not in noms]
        out += tw
        noms |= {i[6:] for i, _n in tw}
        # sources que seul un pilote 32 bits connait (scanner reseau relie par le pont du fabricant, ancien pilote)
        out += [("twain32:" + n, n + " " + _("(TWAIN 32 bits)")) for n in scanners_twain32() if n not in noms]
    elif shutil.which("scanimage"):
        try:
            r = subprocess.run(["scanimage", "-f", "%d|%v %m%n"], capture_output=True, text=True, timeout=30)
            out = [tuple(l.split("|", 1)) for l in r.stdout.splitlines() if "|" in l]
        except Exception:                               # noqa: BLE001
            out = []
    if reseau:
        out += scanners_reseau()
    return out


def _prop(props, ident, valeur):
    for i in range(1, props.Count + 1):
        if props.Item(i).PropertyID == ident:
            try:
                props.Item(i).Value = valeur
            except Exception:
                pass
            return


def _numeriser_windows(device_id, mode, dpi, source):
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:                                   # noqa: BLE001
        pass
    import win32com.client
    dm = win32com.client.Dispatch("WIA.DeviceManager")
    dev = None
    for i in range(1, dm.DeviceInfos.Count + 1):
        if dm.DeviceInfos.Item(i).DeviceID == device_id:
            dev = dm.DeviceInfos.Item(i).Connect()
    if dev is None:
        raise RuntimeError(_('Scanner introuvable'))
    # 3088 : selection chargeur (1) / vitre (2) / recto-verso (4|1)
    _prop(dev.Properties, 3088, {"vitre": 2, "chargeur": 1, "recto_verso": 5}[source])
    _prop(dev.Properties, 3096, 1)   # une page a la fois
    item = dev.Items.Item(1)
    _prop(item.Properties, 6146, WIA_INTENT[mode])
    _prop(item.Properties, 6147, dpi)
    _prop(item.Properties, 6148, dpi)
    images = []
    while True:
        try:
            img = item.Transfer(FORMAT_PNG)
        except Exception as e:
            if images and ("0x80210003" in str(e) or "-2145320957" in str(e)):  # chargeur vide
                break
            if images:
                break
            raise
        images.append(bytes(img.FileData.BinaryData))
        if source == "vitre":
            break
    return images


def _numeriser_linux(device_id, mode, dpi, source):
    tmp = tempfile.mkdtemp()
    m = {"couleur": "Color", "auto": "Color", "gris": "Gray", "nb": "Lineart"}[mode]
    cmd = ["scanimage", "-d", device_id, "--mode", m, "--resolution", str(dpi), "--format=png"]
    if source != "vitre":
        cmd += [f"--batch={tmp}/p%03d.png", "--source", "ADF Duplex" if source == "recto_verso" else "ADF"]
        subprocess.run(cmd, timeout=600)
        return [open(os.path.join(tmp, f), "rb").read() for f in sorted(os.listdir(tmp))]
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    return [r.stdout] if r.stdout else []


def numeriser(device_id, mode="auto", dpi=300, source="chargeur", fenetre=None, interface=False):
    """Renvoie la liste des images (PNG, JPEG ou BMP) numerisees."""
    if device_id.startswith("twain32:"):
        return _numeriser_twain32(device_id[8:], mode, dpi, source, interface)
    if device_id.startswith("twain:"):
        nom = device_id[6:]
        if nom in preferer32():
            return _numeriser_twain32(nom, mode, dpi, source, interface)
        try:
            return _numeriser_twain(nom, mode, dpi, source, fenetre, interface)
        except OuvertureImpossible:
            if nom not in scanners_twain32():
                raise
            # le pilote 64 bits plante a l'ouverture (ex. Avision relie par Virtual Scanner Link) : son pilote
            # 32 bits, celui qu'utilise le logiciel du fabricant, prend le relais pour le reste de la session
            _journal(f"TWAIN {nom} : le pilote 64 bits s'arrête à l'ouverture : essai avec le pilote 32 bits")
            _retenir32(nom)
            return _numeriser_twain32(nom, mode, dpi, source, interface)
    if device_id.startswith("escl:"):
        from . import escl
        return escl.numeriser(device_id[5:], mode, dpi, source, _journal)
    if sys.platform == "win32":
        return _numeriser_windows(device_id, mode, dpi, source)
    return _numeriser_linux(device_id, mode, dpi, source)


def dialogue_windows():
    """Repli : fenetre de numerisation standard de Windows (WIA)."""
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:                                   # noqa: BLE001
        pass
    import win32com.client
    cd = win32com.client.Dispatch("WIA.CommonDialog")
    try:
        img = cd.ShowAcquireImage(1, 0, 0, FORMAT_PNG, False, True, False)
    except Exception as e:                              # noqa: BLE001
        if "-2145320939" in str(e) or "0x80210015" in str(e).lower():
            raise RuntimeError(_("Windows ne connaît aucun scanner WIA sur ce poste : la fenêtre de numérisation de "
                                 "Windows ne peut rien faire. Choisissez le scanner dans la liste (réseau ou TWAIN) ; "
                                 "s'il n'y est pas, installez le pilote 64 bits du fabricant.")) from e
        raise
    return [bytes(img.FileData.BinaryData)] if img else []


# ------------------------------------------------------------------ assemblage
def _page_blanche(gris):
    return (gris < 200).mean() < 0.003


def assembler(images, mode, dpi, supprimer_blanches=True, redresser=True):
    """Images -> PDF A4 compact. Mode auto : noir et blanc net si la page est du texte."""
    from PIL import Image
    import cv2
    from .scan import angle_inclinaison, redresser as tourner, nettoyer
    doc = fitz.open()
    for octets in images:
        im = Image.open(io.BytesIO(octets))
        coul = np.array(im.convert("RGB"))
        gris = cv2.cvtColor(coul, cv2.COLOR_RGB2GRAY)
        if supprimer_blanches and _page_blanche(gris):
            continue
        a = angle_inclinaison(gris) if redresser else 0
        if abs(a) > 0.05:
            gris = tourner(gris, a)
            M = cv2.getRotationMatrix2D((coul.shape[1] / 2, coul.shape[0] / 2), a, 1)
            coul = cv2.warpAffine(coul, M, (coul.shape[1], coul.shape[0]), borderValue=(255, 255, 255))
        couleurs = np.abs(coul.astype(int) - coul.mean(axis=2, keepdims=True)).mean()
        buf = io.BytesIO()
        if mode == "nb" or (mode == "auto" and couleurs < 6):
            Image.fromarray(nettoyer(gris, dpi)).convert("1").save(buf, "TIFF", compression="group4", dpi=(dpi, dpi))
        elif mode == "gris":
            Image.fromarray(gris).save(buf, "JPEG", quality=70, dpi=(dpi, dpi))
        else:
            Image.fromarray(coul).save(buf, "JPEG", quality=72, dpi=(dpi, dpi))
        h, w = gris.shape
        page = doc.new_page(width=w * 72 / dpi, height=h * 72 / dpi)
        img = fitz.open(stream=buf.getvalue())
        page.insert_image(page.rect, stream=buf.getvalue())
    return doc
