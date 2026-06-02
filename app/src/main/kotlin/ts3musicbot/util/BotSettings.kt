package ts3musicbot.util

import org.yaml.snakeyaml.Yaml
import java.io.File
import java.io.FileInputStream

// main config.yml model
class ServerConfig {
    var address: String = "ts.example.com"
    var port: Int = 9987
    var password: String = ""
}

class BotConfig {
    var nickname: String = "MusicBot"
    var defaultChannelId: Int = 12
    var reconnect: Boolean = true
    var autoJoin: Boolean = true
    var channelName: String = ""
    var channelPassword: String = ""
}

class AudioConfig {
    var volume: Int = 50
    var maxQueueSize: Int = 100
    var bufferMs: Int = 5000
    var opusPassthrough: Boolean = true
    var streamOnly: Boolean = true
}

class LimitsConfig {
    var maxPlaylistTracks: Int = 25
    var maxSongLengthMinutes: Int = 15
    var idleDisconnectMinutes: Int = 10
}

class PerformanceConfig {
    var workerThreads: Int = 1
    var asyncLoaderThreads: Int = 1
    var providerThreads: Int = 1
    var gcOptimized: Boolean = true
    var lowMemoryMode: Boolean = true
}

class MainConfig {
    val server = ServerConfig()
    val bot = BotConfig()
    val audio = AudioConfig()
    val limits = LimitsConfig()
    val performance = PerformanceConfig()
}

// commands.yml model
class CommandsConfig {
    var prefix: String = "!"
    var commands: Map<String, String> = emptyMap()
}

// providers.yml model
class SpotifyProviderConfig {
    var mode: String = "auto"
    var clientId: String = ""
    var clientSecret: String = ""
}

class SoundCloudProviderConfig {
    var mode: String = "auto"
    var clientId: String = ""
}

class YouTubeProviderConfig {
    var mode: String = "auto"
    var apiKey: String = ""
}

class SearchConfig {
    var providerOrder: List<String> = listOf("spotify", "soundcloud", "youtube")
    var timeoutMs: Map<String, Int> = mapOf("spotify" to 2000, "soundcloud" to 2000, "youtube" to 2000)
    var retryFailedProvider: Boolean = false
}

class StreamingConfig {
    var metadataMinimalMode: Boolean = true
    var preloadNextTrack: Boolean = false
    var cacheTracks: Boolean = false
    var cacheMetadata: Boolean = true
}

class BootConfig {
    var failIfNoProviderAvailable: Boolean = true
    var startupProviderCheck: Boolean = true
    var startupTimeoutMs: Int = 10000
}

class ProvidersConfig {
    val spotify = SpotifyProviderConfig()
    val soundcloud = SoundCloudProviderConfig()
    val youtube = YouTubeProviderConfig()
    val search = SearchConfig()
    val streaming = StreamingConfig()
    val boot = BootConfig()
}

// permissions.yml model
class PermissionsDetails {
    var enabled: Boolean = true
    var requiredBadges: List<String> = emptyList()
    var requiredServerGroups: List<Int> = emptyList()
    var cacheBadges: Boolean = true
    var cacheTtlSeconds: Int = 300
    var denyMessage: String = "You are not allowed to use music commands."
    var publicCommands: List<String> = listOf("np", "q", "src", "ping")
}

class PermissionsConfig {
    val permissions = PermissionsDetails()
}

class BotSettings(
    var apiKey: String = "",
    var serverAddress: String = "ts.example.com",
    var serverPort: Int = 9987,
    var serverPassword: String = "",
    var channelName: String = "",
    var channelPassword: String = "",
    var channelFilePath: String = "",
    var nickname: String = "MusicBot",
    var market: String = "US",
    var spotifyPlayer: String = "spotify",
    var spotifyUsername: String = "",
    var spotifyPassword: String = "",
    var useOfficialTsClient: Boolean = false,
    var acceptTsLicense: Boolean = true,
    var scVolume: Int = 50,
    var ytVolume: Int = 50,
    var bcVolume: Int = 50,
    var ytApiKey: String = "",
    var spApiKey: String = "",
    var spClientId: String = "",
    var spClientSecret: String = "",
) {
    companion object {
        lateinit var main: MainConfig
        lateinit var commands: CommandsConfig
        lateinit var providers: ProvidersConfig
        lateinit var permissions: PermissionsConfig

        fun loadAll(
            mainFile: File,
            commandsFile: File,
            providersFile: File,
            permissionsFile: File
        ): BotSettings {
            val settings = BotSettings()
            val yaml = Yaml()

            // 1. Main config.yml
            main = MainConfig()
            if (mainFile.exists()) {
                try {
                    FileInputStream(mainFile).use { fis ->
                        val map = yaml.load<Map<String, Any>>(fis) ?: emptyMap()
                        (map["server"] as? Map<*, *>)?.let { s ->
                            main.server.address = s["address"] as? String ?: main.server.address
                            main.server.port = (s["port"] as? Number)?.toInt() ?: main.server.port
                            main.server.password = s["password"] as? String ?: main.server.password
                        }
                        (map["bot"] as? Map<*, *>)?.let { b ->
                            main.bot.nickname = b["nickname"] as? String ?: main.bot.nickname
                            main.bot.defaultChannelId = (b["default_channel_id"] as? Number)?.toInt() ?: main.bot.defaultChannelId
                            main.bot.reconnect = b["reconnect"] as? Boolean ?: main.bot.reconnect
                            main.bot.autoJoin = b["auto_join"] as? Boolean ?: main.bot.autoJoin
                            main.bot.channelName = b["channel_name"] as? String ?: main.bot.channelName
                            main.bot.channelPassword = b["channel_password"] as? String ?: main.bot.channelPassword
                        }
                        (map["audio"] as? Map<*, *>)?.let { a ->
                            main.audio.volume = (a["volume"] as? Number)?.toInt() ?: main.audio.volume
                            main.audio.maxQueueSize = (a["max_queue_size"] as? Number)?.toInt() ?: main.audio.maxQueueSize
                            main.audio.bufferMs = (a["buffer_ms"] as? Number)?.toInt() ?: main.audio.bufferMs
                            main.audio.opusPassthrough = a["opus_passthrough"] as? Boolean ?: main.audio.opusPassthrough
                            main.audio.streamOnly = a["stream_only"] as? Boolean ?: main.audio.streamOnly
                        }
                        (map["limits"] as? Map<*, *>)?.let { l ->
                            main.limits.maxPlaylistTracks = (l["max_playlist_tracks"] as? Number)?.toInt() ?: main.limits.maxPlaylistTracks
                            main.limits.maxSongLengthMinutes = (l["max_song_length_minutes"] as? Number)?.toInt() ?: main.limits.maxSongLengthMinutes
                            main.limits.idleDisconnectMinutes = (l["idle_disconnect_minutes"] as? Number)?.toInt() ?: main.limits.idleDisconnectMinutes
                        }
                        (map["performance"] as? Map<*, *>)?.let { p ->
                            main.performance.workerThreads = (p["worker_threads"] as? Number)?.toInt() ?: main.performance.workerThreads
                            main.performance.asyncLoaderThreads = (p["async_loader_threads"] as? Number)?.toInt() ?: main.performance.asyncLoaderThreads
                            main.performance.providerThreads = (p["provider_threads"] as? Number)?.toInt() ?: main.performance.providerThreads
                            main.performance.gcOptimized = p["gc_optimized"] as? Boolean ?: main.performance.gcOptimized
                            main.performance.lowMemoryMode = p["low_memory_mode"] as? Boolean ?: main.performance.lowMemoryMode
                        }
                    }
                } catch (e: Exception) {
                    println("[WARN] Failed to parse config.yml: ${e.message}. Using defaults.")
                }
            }

            // 2. Commands Config
            commands = CommandsConfig()
            if (commandsFile.exists()) {
                try {
                    FileInputStream(commandsFile).use { fis ->
                        val map = yaml.load<Map<String, Any>>(fis) ?: emptyMap()
                        commands.prefix = map["prefix"] as? String ?: commands.prefix
                        val cmds = map["commands"] as? Map<*, *>
                        if (cmds != null) {
                            commands.commands = cmds.entries.associate { it.key.toString() to it.value.toString() }
                        }
                    }
                } catch (e: Exception) {
                    println("[WARN] Failed to parse commands.yml: ${e.message}. Using defaults.")
                }
            }

            // 3. Providers Config
            providers = ProvidersConfig()
            if (providersFile.exists()) {
                try {
                    FileInputStream(providersFile).use { fis ->
                        val map = yaml.load<Map<String, Any>>(fis) ?: emptyMap()
                        (map["spotify"] as? Map<*, *>)?.let { s ->
                            providers.spotify.mode = s["mode"] as? String ?: providers.spotify.mode
                            providers.spotify.clientId = s["client_id"] as? String ?: providers.spotify.clientId
                            providers.spotify.clientSecret = s["client_secret"] as? String ?: providers.spotify.clientSecret
                        }
                        (map["soundcloud"] as? Map<*, *>)?.let { s ->
                            providers.soundcloud.mode = s["mode"] as? String ?: providers.soundcloud.mode
                            providers.soundcloud.clientId = s["client_id"] as? String ?: providers.soundcloud.clientId
                        }
                        (map["youtube"] as? Map<*, *>)?.let { y ->
                            providers.youtube.mode = y["mode"] as? String ?: providers.youtube.mode
                            providers.youtube.apiKey = y["api_key"] as? String ?: providers.youtube.apiKey
                        }
                        (map["search"] as? Map<*, *>)?.let { s ->
                            providers.search.providerOrder = (s["provider_order"] as? List<*>)?.map { it.toString() } ?: providers.search.providerOrder
                            val timeouts = s["timeout_ms"] as? Map<*, *>
                            if (timeouts != null) {
                                providers.search.timeoutMs = timeouts.entries.associate { it.key.toString() to (it.value as Number).toInt() }
                            }
                            providers.search.retryFailedProvider = s["retry_failed_provider"] as? Boolean ?: providers.search.retryFailedProvider
                        }
                        (map["streaming"] as? Map<*, *>)?.let { s ->
                            providers.streaming.metadataMinimalMode = s["metadata_minimal_mode"] as? Boolean ?: providers.streaming.metadataMinimalMode
                            providers.streaming.preloadNextTrack = s["preload_next_track"] as? Boolean ?: providers.streaming.preloadNextTrack
                            providers.streaming.cacheTracks = s["cache_tracks"] as? Boolean ?: providers.streaming.cacheTracks
                            providers.streaming.cacheMetadata = s["cache_metadata"] as? Boolean ?: providers.streaming.cacheMetadata
                        }
                        (map["boot"] as? Map<*, *>)?.let { b ->
                            providers.boot.failIfNoProviderAvailable = b["fail_if_no_provider_available"] as? Boolean ?: providers.boot.failIfNoProviderAvailable
                            providers.boot.startupProviderCheck = b["startup_provider_check"] as? Boolean ?: providers.boot.startupProviderCheck
                            providers.boot.startupTimeoutMs = (b["startup_timeout_ms"] as? Number)?.toInt() ?: providers.boot.startupTimeoutMs
                        }
                    }
                } catch (e: Exception) {
                    println("[WARN] Failed to parse providers.yml: ${e.message}. Using defaults.")
                }
            }

            // 4. Permissions Config
            permissions = PermissionsConfig()
            if (permissionsFile.exists()) {
                try {
                    FileInputStream(permissionsFile).use { fis ->
                        val map = yaml.load<Map<String, Any>>(fis) ?: emptyMap()
                        (map["permissions"] as? Map<*, *>)?.let { p ->
                            permissions.permissions.enabled = p["enabled"] as? Boolean ?: permissions.permissions.enabled
                            permissions.permissions.requiredBadges = (p["required_badges"] as? List<*>)?.map { it.toString() } ?: permissions.permissions.requiredBadges
                            permissions.permissions.requiredServerGroups = (p["required_server_groups"] as? List<*>)?.map { (it as Number).toInt() } ?: permissions.permissions.requiredServerGroups
                            permissions.permissions.cacheBadges = p["cache_badges"] as? Boolean ?: permissions.permissions.cacheBadges
                            permissions.permissions.cacheTtlSeconds = (p["cache_ttl_seconds"] as? Number)?.toInt() ?: permissions.permissions.cacheTtlSeconds
                            permissions.permissions.denyMessage = p["deny_message"] as? String ?: permissions.permissions.denyMessage
                            permissions.permissions.publicCommands = (p["public_commands"] as? List<*>)?.map { it.toString() } ?: permissions.permissions.publicCommands
                        }
                    }
                } catch (e: Exception) {
                    println("[WARN] Failed to parse permissions.yml: ${e.message}. Using defaults.")
                }
            }

            // Populate BotSettings values for backwards compatibility
            settings.serverAddress = main.server.address
            settings.serverPort = main.server.port
            settings.serverPassword = main.server.password
            settings.nickname = main.bot.nickname
            settings.channelName = main.bot.channelName
            settings.channelPassword = main.bot.channelPassword
            settings.useOfficialTsClient = false
            settings.scVolume = main.audio.volume
            settings.ytVolume = main.audio.volume
            settings.bcVolume = main.audio.volume
            
            settings.spClientId = providers.spotify.clientId
            settings.spClientSecret = providers.spotify.clientSecret
            settings.ytApiKey = providers.youtube.apiKey

            return settings
        }
    }
}
