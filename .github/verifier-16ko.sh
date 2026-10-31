#!/bin/bash
# Google Play exige des bibliotheques natives 64 bits (arm64-v8a, x86_64) alignees sur 16 Ko : verification dans le .aab
aab="$1"; d=$(mktemp -d); unzip -q -o "$aab" 'base/lib/*' -d "$d" 2>/dev/null
ok=1
for so in $(find "$d" -path '*arm64-v8a*' -name '*.so' -o -path '*x86_64*' -name '*.so'); do
  for a in $(objdump -p "$so" | awk '/LOAD/ {print $NF}'); do
    if [ $(( a )) -lt 16384 ]; then echo "::warning title=16 Ko::$(basename "$(dirname "$so")")/$(basename "$so") aligne sur $a"; ok=0; fi
  done
done
[ $ok = 1 ] && echo "::notice title=16 Ko::bibliotheques natives alignees sur 16 Ko 64 bits alignees sur 16 Ko (accepte par Google Play)"
exit 0
