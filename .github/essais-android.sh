#!/usr/bin/env bash
# Essais sur le telephone simule (lance depuis android/ par android-emulator-runner), sur la version publiee (R8)
adb logcat -c || true
timeout 35m gradle --no-daemon connectedReleaseAndroidTest > essais.log 2>&1
r=$?
if [ $r -ne 0 ]; then
  [ $r -eq 124 ] && echo "::error title=Essai Android::essais bloques plus de 35 minutes"
  grep -E "FAILED|Exception|AssertionError|expected|^e: |ERROR" essais.log | head -40 | cut -c1-300 | while IFS= read -r l; do echo "::error title=Essai Android::$l"; done
  tail -n 60 essais.log
  echo "----- journal du telephone (plantages, PhilPDF) -----"
  adb logcat -d 2>/dev/null | grep -E "AndroidRuntime|FATAL|philpdf|TestRunner|Instrumentation|R8|ClassNotFound|NoSuchMethod|NoClassDef|UnsatisfiedLink" | tail -150 | cut -c1-300
  exit 1
fi
grep -E "Tests? .*(passed|finished)|BUILD SUCCESSFUL" essais.log | tail -3
echo "::notice title=Essais Android::tous les essais passent"
