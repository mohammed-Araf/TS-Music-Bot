import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    application
    kotlin("jvm") version "2.3.21"
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
    maven(url = "https://maven.lavalink.dev/releases")
}

dependencies {
    testImplementation(kotlin("test"))
    implementation(platform("org.jetbrains.kotlin:kotlin-bom"))
    implementation("org.json:json:20251224")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core-jvm:1.11.0")
    implementation("com.github.bettehem:ts3j:1.0.21")
    implementation("dev.arbjerg:lavaplayer:2.2.6")
    implementation("dev.lavalink.youtube:youtube-plugin:1.11.4")
    implementation("org.yaml:snakeyaml:2.3")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}

tasks.test {
    useJUnitPlatform()
}
kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.JVM_21
    }
    jvmToolchain(21)
}

application {
    mainClass = "ts3musicbot.Main"
}

java {
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
}

tasks.shadowJar {
    archiveBaseName.set("ts3-musicbot")
    archiveFileName.set("ts3-musicbot.jar")
    mergeServiceFiles()
    manifest {
        attributes(mapOf("Main-Class" to application.mainClass))
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
