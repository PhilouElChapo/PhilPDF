pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://maven.ghostscript.com/") }     // MuPDF (Artifex), meme moteur que PyMuPDF
        maven { url = uri("https://jitpack.io") }                  // Tesseract4Android (OCR)
    }
}
rootProject.name = "PhilPDF"
include(":app")
