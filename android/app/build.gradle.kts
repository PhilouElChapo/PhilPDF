plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Numero propre a Android (android/version.txt) : l'APK n'est refabrique et publie que si android/ change
val versionPhilpdf: String = rootProject.file("version.txt").readText().trim().ifEmpty { "0.0.0" }
val versionCodePhilpdf: Int = versionPhilpdf.split(".").map { p -> p.filter { it.isDigit() }.toIntOrNull() ?: 0 }
    .let { (it.getOrElse(0) { 0 }) * 1_000_000 + (it.getOrElse(1) { 0 }) * 1_000 + (it.getOrElse(2) { 0 }) }
val clef: String? = System.getenv("ANDROID_KEYSTORE_FILE")

android {
    namespace = "io.github.philouelchapo.philpdf"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.philouelchapo.philpdf"
        minSdk = 26                      // Android 8 (2017)
        targetSdk = 36              // Android 16 : exige par Google Play pour une nouvelle application
        versionCode = versionCodePhilpdf
        versionName = versionPhilpdf
        // essais sur telephone (simule par GitHub a chaque fabrication) : app/src/androidTest
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // PHILPDF_PLAY=1 : paquet pour Google Play (les mises a jour passent par le Play Store, pas par GitHub)
        buildConfigField("boolean", "PLAY_STORE", if (System.getenv("PHILPDF_PLAY") == "1") "true" else "false")
        // meme identifiant Google que PhilPDF Windows : il voit le dossier PhilPDF que Windows a cree (drive.file)
        buildConfigField("String", "GOOGLE_ID", "\"${(System.getenv("GOOGLE_CLIENT_ID") ?: "").trim()}\"")
        buildConfigField("String", "GOOGLE_SECRET", "\"${(System.getenv("GOOGLE_CLIENT_SECRET") ?: "").trim()}\"")
        // OneDrive, Dropbox, Box : memes applications que PhilPDF Windows (espaces colles par erreur retires)
        for (n in listOf("ONEDRIVE", "DROPBOX", "BOX")) {
            buildConfigField("String", "${n}_ID", "\"${(System.getenv("${n}_CLIENT_ID") ?: "").filterNot { it.isWhitespace() }}\"")
            buildConfigField("String", "${n}_SECRET", "\"${(System.getenv("${n}_CLIENT_SECRET") ?: "").filterNot { it.isWhitespace() }}\"")
        }
    }

    // un APK par type de processeur (moins de 30 Mo chacun, demande par IzzyOnDroid) + un APK universel
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a", "x86_64")
            isUniversalApk = true
        }
    }

    signingConfigs {
        create("philpdf") {
            if (clef != null) {
                storeFile = file(clef)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            // Google Play demande un code optimise (R8 : raccourci et obscurci) ; regles dans proguard-rules.pro
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            testProguardFiles("proguard-essais.pro")
            signingConfig = if (clef != null) signingConfigs.getByName("philpdf") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging {
        resources { excludes += setOf("META-INF/versions/9/OSGI-INF/MANIFEST.MF", "META-INF/DEPENDENCIES") }
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

// numero de version different par processeur (exige par les depots F-Droid / IzzyOnDroid)
val codesAbi = mapOf("armeabi-v7a" to 1, "arm64-v8a" to 2, "x86_64" to 3)
androidComponents {
    onVariants { v ->
        v.outputs.forEach { o ->
            val abi = o.filters.find { it.filterType == com.android.build.api.variant.FilterConfiguration.FilterType.ABI }?.identifier
            o.versionCode.set(versionCodePhilpdf * 10 + (codesAbi[abi] ?: 0))
        }
    }
}

dependencies {
    implementation("com.artifex.mupdf:fitz:1.28.5")   // version suivie par .github/workflows/mupdf.yml
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    // signature numerique : CMS (PKCS#7), lecture des .pfx, horodatage (meme principe que pyHanko sous Windows)
    implementation("org.bouncycastle:bcpkix-jdk18on:1.78.1")
    // reconnaissance du texte des pages scannees (Tesseract, comme PhilPDF Windows), sur le telephone, sans Internet
    implementation("cz.adaptech.tesseract4android:tesseract4android:4.9.0")
    // numeriser un document : le scanner de Google s'il est sur le telephone (sinon appareil photo + recadrage maison)
    implementation("com.google.android.gms:play-services-mlkit-document-scanner:16.0.0-beta1")
    implementation("androidx.exifinterface:exifinterface:1.3.7")
}

// Nouveautes (readme.txt du depot) livrees dans l'APK : Accueil > Aide > Nouveautes
val copierNouveautes by tasks.registering(Copy::class) {
    from(rootProject.file("../readme.txt"))
    // reconnaissance du texte (OCR) : meme langue francaise que PhilPDF Windows (tessdata du depot)
    from(rootProject.file("../tessdata/fra.traineddata")) { into("tessdata") }
    into(layout.buildDirectory.dir("nouveautes"))
}
android.sourceSets.getByName("main").assets.srcDir(layout.buildDirectory.dir("nouveautes").get().asFile)
tasks.named("preBuild") { dependsOn(copierNouveautes) }
