"""Sur GitHub Actions, toute erreur d'un test devient une annotation lisible (titre + trace)."""
import os, sys, traceback

for _f in (sys.stdout, sys.stderr):                      # console Windows (cp1252) : « → », « ≤ »... sans erreur
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                     # noqa: BLE001
        pass

if os.environ.get("GITHUB_ACTIONS"):
    def _crochet(t, v, tb):
        trace = "".join(traceback.format_exception(t, v, tb))[-3000:]
        print("::error title=" + os.path.basename(sys.argv[0]) + "::" + trace.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))
        sys.__excepthook__(t, v, tb)
    sys.excepthook = _crochet
