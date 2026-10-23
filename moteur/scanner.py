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


def scanners():
    """[(identifiant, nom)] des scanners disponibles."""
    if sys.platform == "win32":
        try:
            import win32com.client
            dm = win32com.client.Dispatch("WIA.DeviceManager")
            out = []
            for i in range(1, dm.DeviceInfos.Count + 1):
                info = dm.DeviceInfos.Item(i)
                if info.Type == 1:   # scanner
                    out.append((info.DeviceID, info.Properties("Name").Value))
            return out
        except Exception:
            return []
    if shutil.which("scanimage"):
        try:
            r = subprocess.run(["scanimage", "-f", "%d|%v %m%n"], capture_output=True, text=True, timeout=30)
            return [tuple(l.split("|", 1)) for l in r.stdout.splitlines() if "|" in l]
        except Exception:
            return []
    return []


def _prop(props, ident, valeur):
    for i in range(1, props.Count + 1):
        if props.Item(i).PropertyID == ident:
            try:
                props.Item(i).Value = valeur
            except Exception:
                pass
            return


def _numeriser_windows(device_id, mode, dpi, source):
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


def numeriser(device_id, mode="auto", dpi=300, source="chargeur"):
    """Renvoie la liste des images (PNG) numerisees."""
    if sys.platform == "win32":
        return _numeriser_windows(device_id, mode, dpi, source)
    return _numeriser_linux(device_id, mode, dpi, source)


def dialogue_windows():
    """Repli : fenetre de numerisation standard de Windows."""
    import win32com.client
    cd = win32com.client.Dispatch("WIA.CommonDialog")
    img = cd.ShowAcquireImage(1, 0, 0, FORMAT_PNG, False, True, False)
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
            Image.fromarray(nettoyer(gris)).convert("1").save(buf, "TIFF", compression="group4", dpi=(dpi, dpi))
        elif mode == "gris":
            Image.fromarray(gris).save(buf, "JPEG", quality=70, dpi=(dpi, dpi))
        else:
            Image.fromarray(coul).save(buf, "JPEG", quality=72, dpi=(dpi, dpi))
        h, w = gris.shape
        page = doc.new_page(width=w * 72 / dpi, height=h * 72 / dpi)
        img = fitz.open(stream=buf.getvalue())
        page.insert_image(page.rect, stream=buf.getvalue())
    return doc
