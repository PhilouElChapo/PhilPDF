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
    }
}
rootProject.name = "PhilPDF"
include(":app")
