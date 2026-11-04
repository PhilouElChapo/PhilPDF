# PhilPDF : code raccourci et obscurci pour Google Play (R8), sans casser ce qui est appele par nom.
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod,SourceFile,LineNumberTable

# PhilPDF lui-meme : garde (petit) ; les essais sur telephone appellent ses classes
-keep class io.github.philouelchapo.philpdf.** { *; }

# MuPDF : la bibliotheque native rappelle ses classes Java par leur nom (JNI)
-keep class com.artifex.mupdf.** { *; }

# Tesseract (reconnaissance du texte) : JNI aussi
-keep class com.googlecode.tesseract.** { *; }

# BouncyCastle (signature numerique) : les algorithmes sont charges par leur nom
-keep class org.bouncycastle.jcajce.provider.** { *; }
-keep class org.bouncycastle.jce.provider.** { *; }
-keep class org.bouncycastle.pqc.jcajce.provider.** { *; }
-dontwarn org.bouncycastle.**
-dontwarn javax.naming.**
