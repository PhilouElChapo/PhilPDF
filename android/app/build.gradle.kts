plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Meme numero de version que PhilPDF Windows et Linux (app/config.py) : une seule version par publication
val versionPhilpdf: String = Regex("VERSION = \"([^\"]+)\"")
    .find(rootProject.file("../app/config.py").readText())?.groupValues?.get(1) ?: "0.0.0"
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
        buildConfigField("String", "GOOGLE_ID", "\"${System.getenv("GOOGLE_CLIENT_ID") ?: ""}\"")
        buildConfigField("String", "GOOGLE_SECRET", "\"${System.getenv("GOOGLE_CLIENT_SECRET") ?: ""}\"")
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
