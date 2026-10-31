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
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.philouelchapo.philpdf"
        minSdk = 26                      // Android 8 (2017)
        targetSdk = 35
        versionCode = versionCodePhilpdf
        versionName = versionPhilpdf
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
            isMinifyEnabled = false
            signingConfig = if (clef != null) signingConfigs.getByName("philpdf") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
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
    implementation("com.artifex.mupdf:fitz:1.28.5")
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}

// Nouveautes (readme.txt du depot) livrees dans l'APK : Accueil > Aide > Nouveautes
val copierNouveautes by tasks.registering(Copy::class) {
    from(rootProject.file("../readme.txt"))
    into(layout.buildDirectory.dir("nouveautes"))
}
android.sourceSets.getByName("main").assets.srcDir(layout.buildDirectory.dir("nouveautes").get().asFile)
tasks.named("preBuild") { dependsOn(copierNouveautes) }
