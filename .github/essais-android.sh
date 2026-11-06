#!/usr/bin/env bash
# Essais sur le telephone simule (lance depuis android/ par android-emulator-runner)
# 1) essais complets du moteur ; 2) la version publiee (optimisee par R8) s'installe et demarre sans planter
# 0) langues : aucun texte ne manque en francais, allemand, espagnol, italien (memes %1$s)
python3 ../tests/test_langues_android.py || { echo "::error title=Langues Android::textes manquants ou formats differents"; exit 1; }
adb logcat -c || true
timeout 55m gradle --no-daemon connectedDebugAndroidTest > essais.log 2>&1
r=$?
if [ $r -ne 0 ]; then
  [ $r -eq 124 ] && echo "::error title=Essai Android::essais bloques plus de 55 minutes"
  grep -E "FAILED|Exception|AssertionError|expected|^e: |ERROR" essais.log | head -40 | cut -c1-300 | while IFS= read -r l; do echo "::error title=Essai Android::$l"; done
  tail -n 60 essais.log
  # textes coupes (TestsTronques) : chaque ecran et ce qui ne tient pas
  adb logcat -d -s PhilTronque:* 2>/dev/null | sed 's/^.*PhilTronque: //' | head -120 | while IFS= read -r l; do echo "::error title=Texte coupe Android::$l"; done
  adb logcat -d 2>/dev/null | grep -E "AndroidRuntime|FATAL|philpdf" | tail -80 | cut -c1-300
  exit 1
fi
grep -E "Tests? .*(passed|finished)|BUILD SUCCESSFUL" essais.log | tail -3

# --- version publiee, optimisee : demarrage (ecran d'accueil)
timeout 20m gradle --no-daemon assembleRelease > release.log 2>&1 || { tail -n 40 release.log; echo "::error title=Essai Android::fabrication de la version publiee impossible"; exit 1; }
apk=$(ls app/build/outputs/apk/release/*x86_64*.apk | head -1)
adb uninstall io.github.philouelchapo.philpdf >/dev/null 2>&1 || true
adb install -r "$apk" || { echo "::error title=Essai Android::installation de la version publiee impossible"; exit 1; }
adb logcat -c || true
adb shell am start -W -n io.github.philouelchapo.philpdf/.MainActivity
sleep 12
if ! adb shell pidof io.github.philouelchapo.philpdf >/dev/null; then
  echo "::error title=Essai Android::la version publiee (R8) se ferme au demarrage"
  adb logcat -d | grep -E "AndroidRuntime|FATAL" -A20 | head -60 | cut -c1-300
  exit 1
fi
if adb logcat -d | grep -q "FATAL EXCEPTION"; then
  echo "::error title=Essai Android::plantage de la version publiee (R8)"
  adb logcat -d | grep -E "FATAL EXCEPTION" -A25 | head -60 | cut -c1-300
  exit 1
fi
echo "::notice title=Essais Android::tous les essais passent, et la version publiee (R8) demarre sans planter"
