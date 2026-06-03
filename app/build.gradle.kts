import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    application
    kotlin("jvm") version "2.3.21"
    id("org.openjfx.javafxplugin") version "0.1.0"
    id("com.gradleup.shadow") version "9.4.1"
    id("org.jmailen.kotlinter") version "5.4.2"
    id("java")
}

group = "ts3-musicbot"
version = "master"

repositories {
    mavenCentral()
    gradlePluginPortal()
    maven(url = "https://jitpack.io")
}

dependencies {
    testImplementation(kotlin("test"))
    implementation(platform("org.jetbrains.kotlin:kotlin-bom"))
    implementation("org.json:json:20251224")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core-jvm:1.11.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-javafx:1.11.0")
    implementation("com.github.bettehem:ts3j:1.0.21")
    implementation("org.openjfx:javafx-controls:11")
}

tasks.test {
    useJUnitPlatform()
}
kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.JVM_11
    }
    jvmToolchain(11)
}

// JavaFX modules to include
javafx {
    version = "11"
    modules("javafx.controls")
}

application {
    // Define the main class for the application.
    mainClass = "ts3musicbot.Main"
}

java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}

tasks.shadowJar {
    archiveBaseName.set("ts3-musicbot")
    archiveFileName.set("ts3-musicbot.jar")
    mergeServiceFiles()
    minimize()
    manifest {
        attributes(mapOf("Main-Class" to application.mainClass))
    }
    dependencies {
        include(dependency("org.jetbrains.kotlin:kotlin-stdlib:2.3.21"))
        include(dependency("org.jetbrains.kotlinx:kotlinx-coroutines-core-jvm:1.11.0"))
        include(dependency("org.jetbrains.kotlinx:kotlinx-coroutines-javafx:1.11.0"))
        include(dependency("org.json:json:20251224"))
        include(dependency("com.github.bettehem:ts3j:1.0.21"))
    }
}

tasks {
    assemble {
        dependsOn(shadowJar)
    }
    startScripts {
        dependsOn(shadowJar)
    }
    distTar {
        enabled = false
    }
    distZip {
        enabled = false
    }
    jar {
        enabled = false
    }
}
