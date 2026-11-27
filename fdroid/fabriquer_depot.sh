#!/usr/bin/env bash
# Fabrique le depot F-Droid de PhilPDF dans $1 (dossier de sortie, ex. site/fdroid).
# Prend les APK par processeur des N dernieres versions Android publiees sur GitHub
# (les memes fichiers, signes avec la clef PhilPDF), ecrit la fiche et signe le catalogue
# avec la clef Android (variables FDROID_KEYSTORE, FDROID_KEYSTORE_PASS, FDROID_KEY_ALIAS, FDROID_KEY_PASS).
set -euo pipefail
SORTIE="$(realpath -m "$1")"; N="${FDROID_VERSIONS:-2}"
DEPOT="${GITHUB_REPOSITORY:-PhilouElChapo/PhilPDF}"
ICI="$(cd "$(dirname "$0")" && pwd)"; RACINE="$(cd "$ICI/.." && pwd)"
APPLI=io.github.philouelchapo.philpdf
TRAVAIL="$(mktemp -d)"; cd "$TRAVAIL"
mkdir -p repo metadata

# 1. APK des N dernieres versions Android (un par processeur ; l'universel est inutile ici)
gh api "repos/$DEPOT/releases?per_page=30" \
  --jq '[.[]|select(.tag_name|startswith("android-v"))|select(.draft|not)|select(.prerelease|not)]|.['"0:$N"'][]|.assets[]|select(.name|test("^PhilPDF-(arm64-v8a|armeabi-v7a|x86_64)\\.apk$"))|"\(.id) \(.name) \(.browser_download_url)"' \
  > liste.txt
[ -s liste.txt ] || { echo "::error title=F-Droid::aucun APK Android trouve"; exit 1; }
while read -r id nom url; do
  v=$(echo "$url" | sed -E 's#.*/download/android-v([^/]+)/.*#\1#')
  gh api -H "Accept: application/octet-stream" "repos/$DEPOT/releases/assets/$id" > "repo/PhilPDF-$v-${nom#PhilPDF-}"
done < liste.txt
ls -la repo

# 2. Fiche : reglages communs + textes et icone de fastlane (fr, en, de, es, it)
cp "$ICI/$APPLI.yml" "metadata/$APPLI.yml"
for d in "$RACINE"/fastlane/metadata/android/*/; do
  l=$(basename "$d"); mkdir -p "metadata/$APPLI/$l"
  cp -r "$d"/. "metadata/$APPLI/$l/"
  rm -f "metadata/$APPLI/$l/images/phoneScreenshots/LISEZMOI.txt"
done
ICONE="$RACINE/fastlane/metadata/android/en-US/images/icon.png"

# 3. Reglages du depot (la clef n'est jamais ecrite dans le depot GitHub)
cp "$ICONE" philpdf.png
cat > config.yml <<CONF
repo_url: https://philouelchapo.github.io/PhilPDF/fdroid/repo
repo_name: PhilPDF
repo_icon: philpdf.png
repo_description: >-
  Depot F-Droid officiel de PhilPDF, editeur PDF libre (AGPL v3) de PhilouElChapo.
  Official F-Droid repository of PhilPDF, a free and open-source PDF editor.
  Same APKs as on GitHub, signed with the PhilPDF key.
archive_older: 0
keystore: $FDROID_KEYSTORE
repo_keyalias: $FDROID_KEY_ALIAS
keystorepass: $FDROID_KEYSTORE_PASS
keypass: $FDROID_KEY_PASS
keydname: CN=PhilPDF, O=PhilouElChapo, C=FR
make_current_version_link: false
CONF
chmod 600 config.yml

# 4. Catalogue signe
fdroid update --pretty
test -f repo/index-v2.json && test -f repo/entry.jar && test -f repo/index-v1.jar

# 5. Sortie : seulement repo/ (pas de clef, pas de config)
rm -rf "$SORTIE"; mkdir -p "$SORTIE"
cp -r repo "$SORTIE/repo"
echo "::notice title=F-Droid::$(ls repo/*.apk | wc -l) APK publies dans le depot F-Droid"
cd /; rm -rf "$TRAVAIL"
