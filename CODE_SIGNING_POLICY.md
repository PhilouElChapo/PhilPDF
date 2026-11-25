# Code signing policy

*Politique de signature du code — version française plus bas.*

PhilPDF for Windows (`PhilPDF_Setup.exe` and the programs inside `PhilPDF_portable.zip`) is built only by GitHub Actions
from the public repository [PhilouElChapo/PhilPDF](https://github.com/PhilouElChapo/PhilPDF)
(workflow `.github/workflows/fabriquer.yml`). Nothing is built or signed on a personal computer.

Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org).
*(Planned: Windows releases are not signed yet.)*

## Team roles

| Role | Members |
|---|---|
| Authors (may change the source without further review) | [PhilouElChapo](https://github.com/PhilouElChapo) |
| Reviewers (review every change from outside contributors, such as pull requests) | [PhilouElChapo](https://github.com/PhilouElChapo) |
| Approvers (approve each signing request) | [PhilouElChapo](https://github.com/PhilouElChapo) |

All members use multi-factor authentication on GitHub and SignPath.

## What is signed

Only binaries built from this repository: the PhilPDF programs and the installer. Third-party open-source components
shipped with PhilPDF (Python, Qt / PySide6, MuPDF / PyMuPDF, Tesseract OCR...) keep their own publishers and are
not signed with this certificate.

## Privacy

PhilPDF has no server and sends nothing on its own except the check for a new version on GitHub (which can be turned
off in Preferences). Your documents go to a cloud account or an AI service only when you ask for it.
Full privacy policy: [philouelchapo.github.io/PhilPDF/confidentialite.html](https://philouelchapo.github.io/PhilPDF/confidentialite.html).

---

## Politique de signature du code (français)

PhilPDF pour Windows est fabriqué uniquement par GitHub Actions à partir du dépôt public, jamais sur un ordinateur
personnel. Signature gratuite fournie par SignPath.io, certificat de la SignPath Foundation (prévu : les versions Windows ne sont pas
encore signées). Auteur, relecteur et approbateur :
PhilouElChapo, avec double authentification sur GitHub et SignPath. Seuls les programmes construits depuis ce dépôt
sont signés. Confidentialité : voir le lien ci-dessus.
