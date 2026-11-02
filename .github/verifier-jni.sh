#!/usr/bin/env bash
# Bibliotheque MuPDF Java (fitz) : methodes declarees en Java mais absentes de libmupdf_java.so (appel = plantage).
# Echec si PhilPDF Android en appelle une. Usage : verifier-jni.sh <version, ex. 1.28.5>
set -u   # (pas -e : grep ne trouvant rien dans une classe sans methode native n est pas une erreur)
v="$1"
t=$(mktemp -d)
curl -sSLfo "$t/fitz.aar" "https://maven.ghostscript.com/com/artifex/mupdf/fitz/$v/fitz-$v.aar" || { echo "::error title=MuPDF Java::version $v introuvable"; exit 1; }
cd "$t" && mkdir a && cd a && unzip -q ../fitz.aar && mkdir c && (cd c && unzip -q ../classes.jar)
so=$(find . -path "*arm64-v8a*" -name "*.so" | grep -i mupdf | head -1)
nm -D --defined-only "$so" | awk '{print $3}' | grep '^Java_' | sed 's/__.*//' | sort -u > presents.txt
for f in $(cd c && find . -name "*.class" | sed 's|^\./||;s|\.class$||' | grep -v '\$'); do
  javap -p -cp c "$(echo "$f" | tr '/' '.')" 2>/dev/null | grep ' native ' | sed -E 's/.* ([A-Za-z0-9_]+)\(.*/\1/' | sort -u | while read -r m; do
    echo "Java_$(echo "$f" | sed 's/_/_1/g; s|/|_|g')_$(echo "$m" | sed 's/_/_1/g') $m"
  done
done | sort -u > declares.txt
awk '{print $1}' declares.txt | comm -23 - presents.txt > absentes.txt
echo "MuPDF $v : $(wc -l < declares.txt) methodes natives declarees, $(wc -l < absentes.txt) absentes"
code=0
while read -r sym; do
  m=$(grep "^$sym " declares.txt | awk '{print $2}' | head -1)
  # les methodes privees (readArray...) sont appelees par une methode publique du meme nom de base : on cherche les deux
  base=$(echo "$m" | sed -E 's/(String|Buffer|PDFObject|Integer|Float|Boolean|Array)+$//')
  if grep -rqE "\.($m|$base)\(" "$GITHUB_WORKSPACE/android/app/src/main/java"; then
    echo "::error title=MuPDF Java::$sym absente de la bibliotheque, mais PhilPDF Android appelle $m"; code=1
  else
    echo "::notice title=MuPDF Java::$sym absente (PhilPDF ne s'en sert pas)"
  fi
done < absentes.txt
exit $code
