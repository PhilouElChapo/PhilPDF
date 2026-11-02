#!/usr/bin/env bash
# Essais sur le telephone simule (lance depuis android/ par android-emulator-runner)
gradle --no-daemon connectedDebugAndroidTest > essais.log 2>&1
r=$?
if [ $r -ne 0 ]; then
  grep -E "FAILED|Exception|AssertionError|expected|^e: " essais.log | head -40 | cut -c1-300 | while IFS= read -r l; do echo "::error title=Essai Android::$l"; done
  tail -n 80 essais.log
  exit 1
fi
grep -E "Tests? .*(passed|finished)|BUILD SUCCESSFUL" essais.log | tail -3
echo "::notice title=Essais Android::tous les essais passent"
