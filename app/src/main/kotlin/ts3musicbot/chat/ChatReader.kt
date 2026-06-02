package ts3musicbot.chat

import com.github.manevolent.ts3j.event.TS3Listener
import com.github.manevolent.ts3j.event.TextMessageEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers.IO
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import ts3musicbot.client.Client
import ts3musicbot.client.OfficialTSClient
import ts3musicbot.client.TeamSpeak
import ts3musicbot.services.AppleMusic
import ts3musicbot.services.Bandcamp
import ts3musicbot.services.ServiceType
import ts3musicbot.services.SongLink
import ts3musicbot.services.SoundCloud
import ts3musicbot.services.Spotify
import ts3musicbot.services.YouTube
import ts3musicbot.util.BotSettings
import ts3musicbot.util.CommandList
import ts3musicbot.util.CommandRunner
import ts3musicbot.util.Link
import ts3musicbot.util.LinkType
import ts3musicbot.util.PlayStateListener
import ts3musicbot.util.SearchQuery
import ts3musicbot.util.SearchResult
import ts3musicbot.util.SearchResults
import ts3musicbot.util.SearchType
import ts3musicbot.util.SongQueue
import ts3musicbot.util.Track
import ts3musicbot.util.TrackList
import ts3musicbot.util.Name
import java.util.concurrent.ConcurrentHashMap
import kotlin.time.Duration.Companion.milliseconds

data class UserPermissionCache(
    val badges: List<String>,
    val serverGroups: List<Int>,
    val cachedAt: Long
)

class ChatReader(
    private val client: Client,
    private val botSettings: BotSettings,
    private var onChatUpdateListener: ChatUpdateListener,
    var commandListener: CommandListener,
    private val cmdList: CommandList = CommandList(),
) : PlayStateListener {
    private var shouldRead = false
    private val commandRunner = CommandRunner()
    private val spotify = Spotify(botSettings)
    private val youTube = YouTube(botSettings.ytApiKey)
    private val soundCloud = SoundCloud()
    private val bandcamp = Bandcamp()
    private val appleMusic = AppleMusic(botSettings)
    private val songLink = SongLink(spotify, soundCloud, youTube, bandcamp, appleMusic, botSettings)
    var latestMsgUsername = ""

    internal val permissionsCache = ConcurrentHashMap<Int, UserPermissionCache>()

    @Volatile
    private var songQueue = SongQueue(botSettings, client, spotify, soundCloud, youTube, bandcamp, this)

    init {
        // initialise spotify token
        CoroutineScope(IO).launch {
            try {
                spotify.updateToken()
            } catch (e: Exception) {
                println("[WARN] Failed to initialize Spotify access token: ${e.message}")
            }
        }
    }

    private fun removeTags(text: String): String =
        text.replace("\\[/?URL]|,($|\\s)".toRegex(), "")

    fun startReading(): Boolean {
        return when (client) {
            is TeamSpeak -> {
                client.addListener(
                    object : TS3Listener {
                        override fun onTextMessage(e: TextMessageEvent?) {
                            CoroutineScope(IO).launch {
                                e?.let { chatUpdated(it.message, it.invokerName, it.invokerId) }
                            }
                        }
                    },
                )
                true
            }
            is OfficialTSClient -> {
                shouldRead = true
                val channelFile = client.channelFile
                if (channelFile.isFile) {
                    CoroutineScope(IO).launch {
                        var currentLine = ""
                        while (shouldRead) {
                            val last = channelFile.readLines().lastOrNull() ?: ""
                            if (last != currentLine) {
                                currentLine = last
                                chatUpdated(currentLine)
                            }
                            delay(500.milliseconds)
                        }
                    }
                    true
                } else {
                    false
                }
            }
            else -> false
        }
    }

    fun stopReading() {
        shouldRead = false
    }

    private fun checkPermission(invokerId: Int, invokerName: String, command: String): Boolean {
        if (latestMsgUsername == "__console__" || invokerId == -1) return true

        val perms = BotSettings.permissions.permissions
        if (!perms.enabled) return true

        // Public commands bypass checks
        if (perms.publicCommands.contains(command)) return true

        // If required fields are empty, allow access
        if (perms.requiredBadges.isEmpty() && perms.requiredServerGroups.isEmpty()) return true

        val now = System.currentTimeMillis()
        val cacheEntry = permissionsCache[invokerId]
        val (badges, serverGroups) = if (cacheEntry != null && now - cacheEntry.cachedAt < perms.cacheTtlSeconds * 1000L) {
            Pair(cacheEntry.badges, cacheEntry.serverGroups)
        } else {
            val tsClient = if (client is TeamSpeak) client.getClientInfo(invokerId) else null
            if (tsClient != null) {
                val bList = tsClient.getBadgeGUIDs()?.toList() ?: emptyList()
                val gList = tsClient.getServerGroups()?.toList() ?: emptyList()
                permissionsCache[invokerId] = UserPermissionCache(bList, gList, now)
                Pair(bList, gList)
            } else {
                Pair(emptyList(), emptyList())
            }
        }

        val hasBadge = perms.requiredBadges.any { req -> badges.contains(req) }
        val hasGroup = perms.requiredServerGroups.any { req -> serverGroups.contains(req) }

        if (hasBadge || hasGroup) {
            return true
        }

        printToChat(listOf(perms.denyMessage))
        return false
    }

    fun parseLine(message: String, invokerId: Int = -1) {
        val prefix = BotSettings.commands.prefix
        if (!message.startsWith(prefix) || message.length <= prefix.length) return

        val body = message.substring(prefix.length).trim()
        val parts = body.split("\\s+".toRegex(), 2)
        val cmdAlias = parts[0]
        val cmdArgs = if (parts.size > 1) parts[1] else ""

        val standardCmd = BotSettings.commands.commands.entries.firstOrNull { it.value == cmdAlias }?.key ?: cmdAlias

        if (!checkPermission(invokerId, latestMsgUsername, standardCmd)) {
            return
        }

        CoroutineScope(IO).launch {
            executeCommand(standardCmd, cmdArgs)
        }
    }

    private suspend fun executeCommand(command: String, args: String) {
        when (command) {
            "play" -> {
                if (args.isEmpty()) {
                    printToChat(listOf("Usage: ${BotSettings.commands.prefix}${BotSettings.commands.commands["play"]} <query/link>"))
                    return
                }
                printToChat(listOf("Resolving tracks, please wait..."))
                val tracks = resolvePlayQuery(args)
                if (tracks.isNotEmpty()) {
                    if (tracks.size == 1) {
                        songQueue.addToQueue(tracks.first())
                        printToChat(listOf("Added to queue: ${tracks.first().toShortString()}"))
                    } else {
                        songQueue.addAllToQueue(TrackList(tracks))
                        printToChat(listOf("Added ${tracks.size} tracks to queue."))
                    }
                    songQueue.startQueue()
                } else {
                    printToChat(listOf("Could not resolve any playable tracks."))
                }
            }
            "skip" -> {
                songQueue.skipSong()
                printToChat(listOf("Skipped current track."))
            }
            "stop" -> {
                songQueue.stopQueue()
                printToChat(listOf("Stopped queue and cleared playlist."))
            }
            "pause" -> {
                songQueue.pausePlayback()
            }
            "resume" -> {
                songQueue.resumePlayback()
            }
            "queue" -> {
                val q = songQueue.getQueue()
                if (q.isEmpty()) {
                    printToChat(listOf("The queue is empty."))
                } else {
                    val sb = java.lang.StringBuilder()
                    sb.appendLine("Current Song Queue:")
                    q.forEachIndexed { i, track ->
                        sb.appendLine("${i + 1}. ${track.toShortString()}")
                    }
                    printToChat(listOf(sb.toString()))
                }
            }
            "clear" -> {
                songQueue.clearQueue()
                printToChat(listOf("Song queue cleared."))
            }
            "remove" -> {
                val pos = args.toIntOrNull()
                if (pos != null) {
                    songQueue.deleteTrack(pos - 1)
                    printToChat(listOf("Removed track at position $pos."))
                } else {
                    printToChat(listOf("Usage: remove <index>"))
                }
            }
            "move" -> {
                val indexes = args.split("\\s+".toRegex()).mapNotNull { it.toIntOrNull() }
                if (indexes.size >= 2) {
                    val from = indexes[0] - 1
                    val to = indexes[1] - 1
                    songQueue.moveTracks(arrayListOf(from), to)
                    printToChat(listOf("Moved track from ${from + 1} to ${to + 1}."))
                } else {
                    printToChat(listOf("Usage: move <from_index> <to_index>"))
                }
            }
            "volume" -> {
                if (args.isEmpty()) {
                    printToChat(listOf("Current Volume: ${songQueue.getVolume()}%"))
                } else {
                    val currentVol = songQueue.getVolume()
                    if (args.startsWith("+") || args.startsWith("-")) {
                        val diff = args.toIntOrNull() ?: 0
                        songQueue.setVolume(currentVol + diff)
                    } else {
                        val targetVol = args.toIntOrNull()
                        if (targetVol != null) {
                            songQueue.setVolume(targetVol)
                        }
                    }
                    printToChat(listOf("Volume set to ${songQueue.getVolume()}%"))
                }
            }
            "loop" -> {
                if (args.lowercase() == "queue") {
                    songQueue.isQueueLooping = !songQueue.isQueueLooping
                    songQueue.isLooping = false
                    printToChat(listOf("Queue looping is now ${if (songQueue.isQueueLooping) "ENABLED" else "DISABLED"}."))
                } else {
                    songQueue.isLooping = !songQueue.isLooping
                    songQueue.isQueueLooping = false
                    printToChat(listOf("Track looping is now ${if (songQueue.isLooping) "ENABLED" else "DISABLED"}."))
                }
            }
            "nowplaying" -> {
                val np = songQueue.nowPlaying()
                if (np.title.name.isNotEmpty()) {
                    printToChat(listOf("Now playing: ${np.toShortString()}"))
                } else {
                    printToChat(listOf("Nothing is currently playing."))
                }
            }
            "sources" -> {
                val sb = java.lang.StringBuilder()
                sb.appendLine("Active Audio Providers:")
                BotSettings.providers.search.providerOrder.forEach { provider ->
                    sb.appendLine("- ${provider.uppercase()}")
                }
                printToChat(listOf(sb.toString()))
            }
            "join" -> {
                if (args.isNotEmpty()) {
                    client.joinChannel(args)
                    printToChat(listOf("Attempting to join channel $args..."))
                }
            }
            "leave" -> {
                client.joinChannel()
                printToChat(listOf("Left channel, returning to default."))
            }
            "ping" -> {
                printToChat(listOf("Pong!"))
            }
            else -> {
                printToChat(listOf("Unknown command. Type ${BotSettings.commands.prefix}help for details."))
            }
        }
    }

    private suspend fun resolvePlayQuery(query: String): List<Track> {
        val cleanQuery = removeTags(query).trim()
        if (cleanQuery.isEmpty()) return emptyList()

        val isLink = cleanQuery.startsWith("http://") || cleanQuery.startsWith("https://") || cleanQuery.startsWith("spotify:")
        if (isLink) {
            val link = Link(cleanQuery)
            when (link.serviceType()) {
                ServiceType.SPOTIFY -> {
                    return try {
                        val linkType = link.linkType(spotify)
                        when (linkType) {
                            LinkType.TRACK -> listOf(spotify.fetchTrack(link))
                            LinkType.PLAYLIST -> spotify.fetchPlaylistTracks(link).trackList
                            LinkType.ALBUM -> spotify.fetchAlbumTracks(link).trackList
                            else -> emptyList()
                        }
                    } catch (e: Exception) {
                        println("[WARN] Failed to resolve Spotify link: ${e.message}")
                        emptyList()
                    }
                }
                ServiceType.SOUNDCLOUD -> {
                    return listOf(Track(title = Name("SoundCloud Track"), link = link))
                }
                ServiceType.YOUTUBE -> {
                    return listOf(Track(title = Name("YouTube Track"), link = link))
                }
                else -> {
                    return listOf(Track(title = Name("Direct Stream Link"), link = link))
                }
            }
        } else {
            val providers = BotSettings.providers.search.providerOrder
            for (provider in providers) {
                try {
                    when (provider.lowercase()) {
                        "spotify" -> {
                            val results = spotify.search(SearchType("track"), SearchQuery(cleanQuery), 1)
                            if (results.results.isNotEmpty()) {
                                return listOf(results.results.first().result as Track)
                            }
                        }
                        "soundcloud" -> {
                            val results = soundCloud.search(SearchType("track"), SearchQuery(cleanQuery), 1)
                            if (results.results.isNotEmpty()) {
                                return listOf(results.results.first().result as Track)
                            }
                        }
                        "youtube" -> {
                            val results = youTube.search(SearchType("video"), SearchQuery(cleanQuery), 1)
                            if (results.results.isNotEmpty()) {
                                return listOf(results.results.first().result as Track)
                            }
                        }
                    }
                } catch (e: Exception) {
                    println("[WARN] Search failed for provider $provider: ${e.message}")
                }
            }
        }
        return emptyList()
    }

    private fun printToChat(messages: List<String>) {
        if (latestMsgUsername == "__console__") {
            messages.forEach { println(it) }
        } else {
            for (message in messages) {
                client.sendMsgToChannel(message)
            }
        }
    }

    private suspend fun chatUpdated(
        line: String,
        userName: String = "",
        invokerId: Int = -1,
    ) {
        when (client) {
            is TeamSpeak ->
                withContext(IO) {
                    parseLine(line, invokerId)
                    onChatUpdateListener.onChatUpdated(ChatUpdate(userName, line))
                }
            is OfficialTSClient ->
                when (client.channelFile.extension) {
                    "txt" -> {
                        if (line.startsWith("<")) {
                            latestMsgUsername = line.substringAfter("> ").substringBeforeLast(": ")
                            val userMessage = line.substringAfter("$latestMsgUsername: ")
                            parseLine(userMessage)
                            withContext(IO) {
                                onChatUpdateListener.onChatUpdated(ChatUpdate(latestMsgUsername, userMessage))
                            }
                        }
                    }
                    else -> {
                        println("Error! file format \"${client.channelFile.extension}\" not supported!")
                    }
                }
        }
    }

    override fun onTrackEnded(player: String, track: Track) {
        printToChat(listOf("Track finished: ${track.title.name}"))
    }

    override fun onTrackPaused(player: String, track: Track) {
        printToChat(listOf("Playback paused."))
    }

    override fun onTrackResumed(player: String, track: Track) {
        printToChat(listOf("Playback resumed."))
    }

    override fun onTrackStarted(player: String, track: Track) {
        if (track.title.name.isNotEmpty()) {
            printToChat(listOf("Now playing: ${track.toShortString()}"))
        }
    }

    override fun onTrackStopped(player: String, track: Track) {}
    override fun onAdPlaying() {}
}

class ChatUpdate(
    val userName: String,
    val message: String,
)

interface ChatUpdateListener {
    fun onChatUpdated(update: ChatUpdate)
}

interface CommandListener {
    fun onCommandExecuted(
        command: String,
        output: String,
        extra: Any? = null,
    )

    fun onCommandProgress(
        command: String,
        output: String,
        extra: Any? = null,
    )
}
