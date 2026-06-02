package ts3musicbot

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers.IO
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import ts3musicbot.chat.ChatReader
import ts3musicbot.chat.ChatUpdate
import ts3musicbot.chat.ChatUpdateListener
import ts3musicbot.chat.CommandListener
import ts3musicbot.client.TeamSpeak
import ts3musicbot.util.BotSettings
import ts3musicbot.util.CommandList
import ts3musicbot.util.Console
import ts3musicbot.util.ConsoleUpdateListener
import java.io.File
import kotlin.system.exitProcess

class Main : ChatUpdateListener, CommandListener {
    companion object {
        private lateinit var teamSpeak: TeamSpeak
        private lateinit var chatReader: ChatReader

        @JvmStatic
        fun main(args: Array<String>) {
            println("[BOOT] Starting TeamSpeak Music Bot in Headless Mode...")

            // 1. Load Configurations
            val configDir = File(".")
            val mainFile = File(configDir, "config.yml")
            val commandsFile = File(configDir, "commands.yml")
            val providersFile = File(configDir, "providers.yml")
            val permissionsFile = File(configDir, "permissions.yml")

            if (!mainFile.exists() || !commandsFile.exists() || !providersFile.exists() || !permissionsFile.exists()) {
                println("[FATAL] Configuration files (config.yml, commands.yml, providers.yml, permissions.yml) must exist in the root directory.")
                exitProcess(1)
            }

            println("[BOOT] Loading configurations...")
            val settings = BotSettings.loadAll(mainFile, commandsFile, providersFile, permissionsFile)

            // 2. Perform Provider Validation
            println("[BOOT] Checking active music providers...")
            var activeProviders = 0

            // Spotify Validation
            if (BotSettings.providers.spotify.mode != "off" && BotSettings.providers.spotify.clientId.isNotEmpty()) {
                try {
                    val spotify = ts3musicbot.services.Spotify(settings)
                    runBlocking { spotify.updateToken() }
                    println("[OK] Spotify authenticated successfully.")
                    activeProviders++
                } catch (e: Exception) {
                    println("[WARN] Spotify authentication failed: ${e.message}")
                }
            }

            // SoundCloud Validation (always enabled if mode is not off)
            if (BotSettings.providers.soundcloud.mode != "off") {
                try {
                    val soundCloud = ts3musicbot.services.SoundCloud()
                    soundCloud.updateClientId()
                    println("[OK] SoundCloud streaming initialized. Scraped Client ID: ${soundCloud.clientId}")
                    activeProviders++
                } catch (e: Exception) {
                    println("[WARN] SoundCloud initialization failed: ${e.message}")
                }
            }

            // YouTube Validation
            if (BotSettings.providers.youtube.mode != "off") {
                if (BotSettings.providers.youtube.apiKey.isNotEmpty()) {
                    println("[OK] YouTube provider initialized with custom API key.")
                } else {
                    println("[OK] YouTube provider initialized.")
                }
                activeProviders++
            }

            if (activeProviders == 0 && BotSettings.providers.boot.failIfNoProviderAvailable) {
                println("[FATAL] No active music providers are available. Exiting.")
                exitProcess(1)
            }

            println("[BOOT] Active providers count: $activeProviders")

            // 3. Connect to TeamSpeak Server
            println("[BOOT] Connecting to TeamSpeak server: ${settings.serverAddress}:${settings.serverPort}...")
            teamSpeak = TeamSpeak(settings)

            var connected = false
            try {
                connected = teamSpeak.connect(settings.serverAddress, settings.serverPassword, settings.serverPort)
            } catch (e: Exception) {
                println("[FATAL] Connection failed: ${e.message}")
                if (BotSettings.providers.boot.failIfNoProviderAvailable) {
                    exitProcess(1)
                }
            }

            if (connected) {
                println("[BOOT] Connected successfully.")
                runBlocking {
                    // Try to join default channel
                    val channelName = settings.channelName.ifEmpty { BotSettings.main.bot.defaultChannelId.toString() }
                    println("[BOOT] Joining channel: $channelName...")
                    teamSpeak.joinChannel(channelName, settings.channelPassword)
                }

                // Initialize command runner listener helper
                val dummyCommandList = CommandList()
                val mainInstance = Main()

                chatReader = ChatReader(
                    teamSpeak,
                    settings,
                    mainInstance,
                    mainInstance,
                    dummyCommandList
                )

                if (chatReader.startReading()) {
                    println("[BOOT] MusicBot listener started listening for channel chat commands.")

                    val console = Console(
                        dummyCommandList,
                        object : ConsoleUpdateListener {
                            override fun onCommandIssued(command: String) {
                                if (command.startsWith(BotSettings.commands.prefix)) {
                                    chatReader.latestMsgUsername = "__console__"
                                    chatReader.parseLine(command)
                                }
                            }
                        },
                        teamSpeak
                    )

                    // Keep console listener running
                    runBlocking {
                        console.startConsole()
                    }
                } else {
                    println("[FATAL] Failed to initialize chat reader.")
                    exitProcess(1)
                }
            } else {
                println("[FATAL] Could not connect to the server. Exiting.")
                exitProcess(1)
            }
        }
    }

    override fun onChatUpdated(update: ChatUpdate) {
        println("[CHAT] ${update.userName}: ${update.message}")
    }

    override fun onCommandExecuted(command: String, output: String, extra: Any?) {
        println("[COMMAND-OK] $command -> $output")
    }

    override fun onCommandProgress(command: String, output: String, extra: Any?) {
        println("[COMMAND-PROGRESS] $command -> $output")
    }
}
