"""Scanners en reseau sans pilote (eSCL, « AirScan », « Mopria ») : ceux que Windows 11 installe sans pilote WIA,
et la plupart des imprimantes multifonctions recentes (HP, Canon, Epson, Brother, Xerox...).

Recherche sur le reseau local par mDNS (_uscan._tcp), puis numerisation par HTTP (protocole eSCL). Aucun module a
installer : seulement la bibliotheque standard de Python."""
import socket
import struct
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

SERVICE = "_uscan._tcp.local"
NS = {"scan": "http://schemas.hp.com/imaging/escl/2011/05/03", "pwg": "http://www.pwg.org/schemas/2010/12/sm"}


# ------------------------------------------------------------------ mDNS (minimal)
def _nom(data, i):
    """Nom DNS a la position i (avec les renvois compresses) -> (nom, position apres)."""
    morceaux, fin, sauts = [], None, 0
    while True:
        n = data[i]
        if n == 0:
            i += 1
            break
        if n & 0xC0 == 0xC0:
            if fin is None:
                fin = i + 2
            i = ((n & 0x3F) << 8) | data[i + 1]
            sauts += 1
            if sauts > 20:
                break
            continue
        morceaux.append(data[i + 1:i + 1 + n].decode("utf-8", "replace"))
        i += 1 + n
    return ".".join(morceaux), (fin if fin is not None else i)


def _question(nom):
    q = b"".join(bytes([len(p)]) + p.encode() for p in nom.split(".")) + b"\0"
    return struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + q + struct.pack(">HH", 12, 1)    # PTR, IN


def _lire_reponse(data, enr):
    """Ajoute a enr les enregistrements PTR, SRV, TXT et A de la reponse."""
    try:
        _id, _f, qd, an, ns, ar = struct.unpack(">HHHHHH", data[:12])
        i = 12
        for _ in range(qd):
            _n, i = _nom(data, i)
            i += 4
        for _ in range(an + ns + ar):
            nom, i = _nom(data, i)
            typ, _cl, _ttl, lg = struct.unpack(">HHIH", data[i:i + 10])
            i += 10
            rd = data[i:i + lg]
            if typ == 12:                                   # PTR : instance du service
                enr["ptr"].add(_nom(data, i)[0])
            elif typ == 33:                                 # SRV : port et machine
                _p, _w, port = struct.unpack(">HHH", rd[:6])
                enr["srv"][nom] = (_nom(data, i + 6)[0], port)
            elif typ == 16:                                 # TXT : rs (chemin), ty (modele)
                t, k = {}, 0
                while k < len(rd):
                    n = rd[k]
                    s = rd[k + 1:k + 1 + n].decode("utf-8", "replace")
                    if "=" in s:
                        a, b = s.split("=", 1)
                        t[a.lower()] = b
                    k += 1 + n
                enr["txt"][nom] = t
            elif typ == 1 and lg == 4:                      # A : adresse IPv4
                enr["a"][nom] = socket.inet_ntoa(rd)
            i += lg
    except (IndexError, struct.error, ValueError):
        pass


def chercher(delai=2.5):
    """[(adresse eSCL, nom lisible)] des scanners reseau qui repondent."""
    enr = {"ptr": set(), "srv": {}, "txt": {}, "a": {}}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        s.settimeout(0.3)
        s.bind(("", 0))                                     # port quelconque : les appareils repondent directement
        q = _question(SERVICE)
        fin = time.monotonic() + delai
        envois = 0
        while time.monotonic() < fin:
            if envois < 3 and time.monotonic() > fin - delai + envois * 0.7:
                try:
                    s.sendto(q, ("224.0.0.251", 5353))
                except OSError:
                    pass
                envois += 1
            try:
                data, _src = s.recvfrom(9000)
                _lire_reponse(data, enr)
            except (socket.timeout, OSError):
                pass
    finally:
        s.close()
    out = []
    for inst in sorted(enr["ptr"]):
        if inst not in enr["srv"]:
            continue
        hote, port = enr["srv"][inst]
        ip = enr["a"].get(hote)
        if not ip:
            try:
                ip = socket.gethostbyname(hote)
            except OSError:
                continue
        t = enr["txt"].get(inst, {})
        rs = (t.get("rs") or "eSCL").strip("/")
        nom = t.get("ty") or inst.split("._uscan")[0]
        out.append((f"http://{ip}:{port}/{rs}", nom))
    return out


# ------------------------------------------------------------------ numerisation (eSCL)
def _http(url, corps=None, methode=None, delai=60):
    r = urllib.request.Request(url, data=corps, method=methode or ("POST" if corps is not None else "GET"))
    if corps is not None:
        r.add_header("Content-Type", "text/xml")
    return urllib.request.urlopen(r, timeout=delai)


def capacites(base):
    """Sources proposees (Platen, Feeder, duplex) et formats, d'apres ScannerCapabilities."""
    x = ET.fromstring(_http(base + "/ScannerCapabilities", delai=15).read())
    cap = {"vitre": x.find(".//scan:Platen", NS) is not None, "chargeur": x.find(".//scan:Adf", NS) is not None,
           "recto_verso": x.find(".//scan:AdfDuplexInputCaps", NS) is not None,
           "formats": {e.text for e in x.iter() if e.tag.endswith("DocumentFormatExt") or e.tag.endswith("DocumentFormat")}}
    return cap


def _reglages(source, couleur, dpi, fmt, region=True):
    src = "Platen" if source == "vitre" else "Feeder"
    zone = ("<pwg:ScanRegions><pwg:ScanRegion><pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>"
            "<pwg:XOffset>0</pwg:XOffset><pwg:YOffset>0</pwg:YOffset><pwg:Width>2480</pwg:Width><pwg:Height>3508</pwg:Height>"
            "</pwg:ScanRegion></pwg:ScanRegions>") if region else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<scan:ScanSettings xmlns:scan="{NS["scan"]}" xmlns:pwg="{NS["pwg"]}">'
            "<pwg:Version>2.0</pwg:Version>" + zone +
            f"<pwg:InputSource>{src}</pwg:InputSource>"
            + ("<scan:Duplex>true</scan:Duplex>" if source == "recto_verso" else "") +
            f"<scan:ColorMode>{couleur}</scan:ColorMode><scan:XResolution>{dpi}</scan:XResolution>"
            f"<scan:YResolution>{dpi}</scan:YResolution><pwg:DocumentFormat>{fmt}</pwg:DocumentFormat>"
            f"<scan:DocumentFormatExt>{fmt}</scan:DocumentFormatExt></scan:ScanSettings>").encode()


def numeriser(base, mode="auto", dpi=300, source="chargeur", journal=None):
    """Images (octets JPEG ou PNG) des pages numerisees."""
    couleur = {"couleur": "RGB24", "auto": "RGB24", "gris": "Grayscale8", "nb": "Grayscale8"}[mode]
    try:
        fmts = capacites(base)["formats"]
    except Exception:                                   # noqa: BLE001
        fmts = set()
    fmt = "image/jpeg" if not fmts or "image/jpeg" in fmts else "application/pdf"
    loc = None
    for region in (True, False):                        # certains appareils refusent la zone A4 : leur zone entiere
        try:
            r = _http(base + "/ScanJobs", _reglages(source, couleur, dpi, fmt, region))
            loc = r.headers.get("Location")
            break
        except urllib.error.HTTPError as e:
            if journal:
                journal(f"ScanJobs ({'A4' if region else 'zone entière'}) : {e.code}")
            if e.code == 503:
                raise RuntimeError("scanner occupé, réessayez dans un instant") from e
            if not region:
                raise
    if not loc:
        raise RuntimeError("le scanner n'a pas accepté la demande")
    if loc.startswith("/"):
        hote = base.split("/", 3)
        loc = hote[0] + "//" + hote[2] + loc
    images, occupe = [], 0
    while True:
        try:
            r = _http(loc.rstrip("/") + "/NextDocument", delai=180)
            o = r.read()
            if "pdf" in (r.headers.get("Content-Type") or "") or o[:4] == b"%PDF":
                import pymupdf as fitz
                d = fitz.open("pdf", o)
                images += [p.get_pixmap(dpi=dpi).tobytes("png") for p in d]
            else:
                images.append(o)
            if source == "vitre":
                break
        except urllib.error.HTTPError as e:
            if e.code == 503 and occupe < 30:           # page en cours de numerisation
                occupe += 1
                time.sleep(1)
                continue
            if e.code in (404, 410) or images:          # plus de page (chargeur vide)
                break
            raise
    try:
        _http(loc, methode="DELETE", delai=10).read()
    except Exception:                                   # noqa: BLE001
        pass
    return images
