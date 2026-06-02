package ts3musicbot.util

import com.sedmelluq.discord.lavaplayer.player.DefaultAudioPlayerManager
import com.sedmelluq.discord.lavaplayer.player.AudioPlayerManager
import com.sedmelluq.discord.lavaplayer.player.AudioPlayer
import com.sedmelluq.discord.lavaplayer.player.AudioLoadResultHandler
import com.sedmelluq.discord.lavaplayer.tools.FriendlyException
import com.sedmelluq.discord.lavaplayer.track.AudioPlaylist
import com.sedmelluq.discord.lavaplayer.track.AudioTrack
import com.sedmelluq.discord.lavaplayer.format.StandardAudioDataFormats
import com.sedmelluq.discord.lavaplayer.player.event.AudioEventAdapter
import com.sedmelluq.discord.lavaplayer.track.AudioTrackEndReason

import kotlinx.coroutines.*
import kotlin.coroutines.resume
import java.io.File
import java.util.Collections
import kotlin.collections.ArrayList

import ts3musicbot.client.TeamSpeak
import ts3musicbot.client.TSAudioProvider
import ts3musicbot.services.Spotify
import ts3musicbot.services.SoundCloud
import ts3musicbot.services.YouTube
import ts3musicbot.services.Bandcamp
import ts3musicbot.services.ServiceType

class SongQueue(
    private val botSettings: BotSettings,
    private val teamSpeak: Any,
    private val spotify: Spotify,
    private val soundCloud: SoundCloud,
    private val youTube: YouTube,
    private val bandcamp: Bandcamp,
    private val playStateListener: PlayStateListener,
) : PlayStateListener {

    enum class State {
        QUEUE_PLAYING,
        QUEUE_PAUSED,
        QUEUE_STOPPED,
    }

    private val songQueue = Collections.synchronizedList(ArrayList<Track>())
    private var queueState = State.QUEUE_STOPPED

    private val playerManager: AudioPlayerManager = DefaultAudioPlayerManager()
    private val audioPlayer: AudioPlayer

    var currentTrack: Track = Track()
    var isLooping = false
    var isQueueLooping = false
    private var isSkipping = false

    private var youtubeDisabled = false
    private var consecutiveYtFailures = 0

    init {
        // 1. Configure LavaPlayer output format for standard Little-Endian 16-bit PCM (48kHz for TeamSpeak)
        playerManager.configuration.setOutputFormat(StandardAudioDataFormats.DISCORD_PCM_S16_LE)
        playerManager.setFrameBufferDuration(BotSettings.main.audio.bufferMs)


        // 2. Register SoundCloud source manager
        playerManager.registerSourceManager(com.sedmelluq.discord.lavaplayer.source.soundcloud.SoundCloudAudioSourceManager.createDefault())

        try {
            val youtubePlugin = dev.lavalink.youtube.YoutubeAudioSourceManager(
                dev.lavalink.youtube.clients.Music(),
                dev.lavalink.youtube.clients.AndroidVr(),
                dev.lavalink.youtube.clients.Web(),
                dev.lavalink.youtube.clients.WebEmbedded(),
                dev.lavalink.youtube.clients.Tv()
            )
            
            // Configure PO Token if provided
            val potToken = BotSettings.providers.youtube.potToken
            val visitorData = BotSettings.providers.youtube.visitorData
            if (potToken.isNotEmpty() && visitorData.isNotEmpty()) {
                println("[LAVAPLAYER] Configuring YouTube plugin with PO Token and Visitor Data...")
                try {
                    dev.lavalink.youtube.clients.Web.setPoTokenAndVisitorData(potToken, visitorData)
                    dev.lavalink.youtube.clients.WebEmbedded.setPoTokenAndVisitorData(potToken, visitorData)
                    println("[LAVAPLAYER] PO Token and Visitor Data set successfully.")
                } catch (e: Exception) {
                    println("[LAVAPLAYER] Failed to set PO Token / Visitor Data: ${e.message}")
                }
            }
            
            // Configure OAuth Refresh Token if provided
            val oauthToken = BotSettings.providers.youtube.oauthRefreshToken
            if (oauthToken.isNotEmpty()) {
                try {
                    if (oauthToken.equals("init", ignoreCase = true)) {
                        println("[LAVAPLAYER] Configuring YouTube plugin: Initiating OAuth device flow...")
                        youtubePlugin.useOauth2(null, false)
                    } else {
                        println("[LAVAPLAYER] Configuring YouTube plugin with OAuth Refresh Token...")
                        youtubePlugin.useOauth2(oauthToken, true)
                        println("[LAVAPLAYER] OAuth Refresh Token configured successfully.")
                    }
                } catch (e: Exception) {
                    println("[LAVAPLAYER] Failed to configure OAuth: ${e.message}")
                }
            }

            playerManager.registerSourceManager(youtubePlugin)
            println("[LAVAPLAYER] Registered YouTube and SoundCloud source managers successfully.")
        } catch (e: Exception) {
            println("[LAVAPLAYER] Error registering YouTube source manager: ${e.message}")
        }

        audioPlayer = playerManager.createPlayer()

        // Apply initial volume
        audioPlayer.volume = BotSettings.main.audio.volume

        // Register microphone in ts3j
        if (teamSpeak is TeamSpeak) {
            val provider = TSAudioProvider(audioPlayer)
            teamSpeak.setMicrophone(provider)
            println("[LAVAPLAYER] TSAudioProvider registered on LocalTeamspeakClientSocket.")
        }

        // Add LavaPlayer listener
        audioPlayer.addListener(object : AudioEventAdapter() {
            override fun onTrackEnd(player: AudioPlayer, track: AudioTrack, endReason: AudioTrackEndReason) {
                if (isSkipping) return  // skip handles playNext() explicitly
                if (endReason.mayStartNext) {
                    onLavaTrackEnd()
                }
            }
            override fun onTrackStart(player: AudioPlayer, track: AudioTrack) {
                onLavaTrackStart()
            }
            override fun onTrackException(player: AudioPlayer, track: AudioTrack, exception: FriendlyException) {
                println("[LAVAPLAYER] Error playing track ${track.info.title}: ${exception.message}")
                exception.printStackTrace()
            }
        })
    }

    private fun onLavaTrackStart() {
        queueState = State.QUEUE_PLAYING
        playStateListener.onTrackStarted("lavaplayer", currentTrack)
    }

    private fun onLavaTrackEnd() {
        if (isLooping) {
            // Replay same track
            CoroutineScope(Dispatchers.Default).launch {
                playTrack(currentTrack)
            }
        } else {
            if (isQueueLooping) {
                songQueue.add(currentTrack)
            }
            playStateListener.onTrackEnded("lavaplayer", currentTrack)
            playNext()
        }
    }

    fun getTrackPosition(): Long {
        val track = audioPlayer.playingTrack
        return if (track != null) track.position / 1000 else 0L
    }

    fun getTrackLength(): Long {
        val track = audioPlayer.playingTrack
        return if (track != null) track.duration / 1000 else 0L
    }

    fun addToQueue(track: Track, position: Int? = null): Boolean {
        synchronized(songQueue) {
            if (position != null && position in 0..songQueue.size) {
                songQueue.add(position, track)
            } else {
                songQueue.add(track)
            }
            return true
        }
    }

    fun addAllToQueue(trackList: TrackList, position: Int? = null): Boolean {
        synchronized(songQueue) {
            if (position != null && position in 0..songQueue.size) {
                songQueue.addAll(position, trackList.trackList)
            } else {
                songQueue.addAll(trackList.trackList)
            }
            return true
        }
    }

    fun clearQueue() {
        synchronized(songQueue) {
            songQueue.clear()
        }
    }

    fun deleteTrack(trackOrPosition: Any) {
        synchronized(songQueue) {
            when (trackOrPosition) {
                is Track -> songQueue.remove(trackOrPosition)
                is Int -> if (trackOrPosition in 0 until songQueue.size) songQueue.removeAt(trackOrPosition)
            }
        }
    }

    fun deleteTracks(tracksOrPositions: Any) {
        synchronized(songQueue) {
            if (tracksOrPositions is List<*>) {
                val positions = ArrayList<Int>()
                val tracks = ArrayList<Track>()
                for (item in tracksOrPositions) {
                    when (item) {
                        is Track -> tracks.add(item)
                        is Int -> positions.add(item)
                    }
                }
                songQueue.removeAll(tracks)
                positions.sortedDescending().forEach { pos ->
                    if (pos in 0 until songQueue.size) {
                        songQueue.removeAt(pos)
                    }
                }
            }
        }
    }

    fun moveTracks(positions: ArrayList<Int>, newPosition: Int): Boolean {
        synchronized(songQueue) {
            var targetPos = newPosition.coerceIn(0, songQueue.size)
            val tracksToMove = positions.sorted().mapNotNull { pos ->
                if (pos in 0 until songQueue.size) songQueue[pos] else null
            }
            songQueue.removeAll(tracksToMove)
            songQueue.addAll(targetPos.coerceAtMost(songQueue.size), tracksToMove)
            return true
        }
    }

    fun getQueue(): ArrayList<Track> = synchronized(songQueue) {
        ArrayList(songQueue)
    }

    fun nowPlaying(): Track = currentTrack

    fun shuffleQueue() {
        synchronized(songQueue) {
            songQueue.shuffle()
        }
    }

    fun skipSong() {
        isSkipping = true
        audioPlayer.stopTrack()
        playStateListener.onTrackEnded("lavaplayer", currentTrack)
        playNext()
        isSkipping = false
    }

    fun startQueue() {
        if (queueState == State.QUEUE_STOPPED) {
            playNext()
        }
    }

    fun resumePlayback() {
        audioPlayer.isPaused = false
        queueState = State.QUEUE_PLAYING
        playStateListener.onTrackResumed("lavaplayer", currentTrack)
    }

    fun pausePlayback() {
        audioPlayer.isPaused = true
        queueState = State.QUEUE_PAUSED
        playStateListener.onTrackPaused("lavaplayer", currentTrack)
    }

    fun stopQueue() {
        audioPlayer.stopTrack()
        queueState = State.QUEUE_STOPPED
        currentTrack = Track()
        songQueue.clear()
        playStateListener.onTrackStopped("lavaplayer", Track())
    }

    private fun playNext() {
        synchronized(songQueue) {
            if (songQueue.isNotEmpty()) {
                val nextTrack = songQueue.removeAt(0)
                currentTrack = nextTrack
                queueState = State.QUEUE_PLAYING
                CoroutineScope(Dispatchers.Default).launch {
                    playTrack(nextTrack)
                }
            } else {
                queueState = State.QUEUE_STOPPED
                currentTrack = Track()
                playStateListener.onTrackStopped("lavaplayer", Track())
            }
        }
    }

    private suspend fun playTrack(track: Track) {
        val link = track.link.link
        var audioTrack: AudioTrack? = null

        if (track.link.serviceType() == ServiceType.SPOTIFY) {
            val primaryArtist = track.artists.artists.firstOrNull()?.name?.name ?: ""
            val query = if (primaryArtist.isNotEmpty()) "$primaryArtist ${track.title.name}" else track.title.name
            println("[LAVAPLAYER] Resolving Spotify track: $query")
            audioTrack = searchAndLoad(query)
        } else {
            audioTrack = loadDirect(link)
            if (audioTrack == null) {
                val primaryArtist = track.artists.artists.firstOrNull()?.name?.name ?: ""
                val query = if (primaryArtist.isNotEmpty()) "$primaryArtist ${track.title.name}" else track.title.name
                println("[LAVAPLAYER] Loading direct failed; searching: $query")
                audioTrack = searchAndLoad(query)
            }
        }

        if (audioTrack != null) {
            audioPlayer.playTrack(audioTrack)
        } else {
            println("[LAVAPLAYER] Unplayable track: ${track.title.name}. Skipping...")
            playNext()
        }
    }

    private suspend fun loadDirect(identifier: String): AudioTrack? {
        val result = loadItemWithTimeout(identifier)
        return when (result) {
            is AudioTrack -> result
            is AudioPlaylist -> result.tracks.firstOrNull()
            else -> null
        }
    }

    private suspend fun searchAndLoad(query: String): AudioTrack? {
        // 1. Try custom SoundCloud search first using resolved client ID
        try {
            println("[LAVAPLAYER] Searching SoundCloud for: $query")
            val results = soundCloud.search(ts3musicbot.util.SearchType("track"), ts3musicbot.util.SearchQuery(query))
            val firstResult = results.results.firstOrNull()
            if (firstResult != null) {
                println("[LAVAPLAYER] Found SoundCloud track: ${firstResult.result.name.name} (${firstResult.link.link})")
                val track = loadDirect(firstResult.link.link)
                if (track != null) return track
            } else {
                println("[LAVAPLAYER] SoundCloud search returned no results for: $query")
            }
        } catch (e: Exception) {
            println("[LAVAPLAYER] Custom SoundCloud search failed: ${e.message}")
        }

        // 2. Try LavaPlayer's built-in SoundCloud Search
        val scTrack = loadDirect("scsearch:$query")
        if (scTrack != null) return scTrack

        // 3. Try YouTube Search (if not disabled)
        if (!youtubeDisabled) {
            val ytTrack = loadDirect("ytsearch:$query")
            if (ytTrack != null) {
                consecutiveYtFailures = 0
                return ytTrack
            } else {
                consecutiveYtFailures++
                if (consecutiveYtFailures >= 3) {
                    youtubeDisabled = true
                    println("[WARNING] YouTube provider disabled due to 3 consecutive failures.")
                }
            }
        }
        return null
    }

    private suspend fun loadItemWithTimeout(identifier: String): Any? {
        val timeout = if (identifier.startsWith("ytsearch:") || identifier.contains("youtube") || identifier.contains("youtu.be")) 2000L else 5000L
        return withTimeoutOrNull(timeout) {
            suspendCancellableCoroutine { cont ->
                playerManager.loadItem(identifier, object : AudioLoadResultHandler {
                    override fun trackLoaded(track: AudioTrack) {
                        cont.resume(track)
                    }
                    override fun playlistLoaded(playlist: AudioPlaylist) {
                        cont.resume(playlist)
                    }
                    override fun noMatches() {
                        cont.resume(null)
                    }
                    override fun loadFailed(exception: FriendlyException) {
                        cont.resume(null)
                    }
                })
            }
        }
    }

    fun setVolume(vol: Int) {
        audioPlayer.volume = vol.coerceIn(0, 100)
    }

    fun getVolume(): Int {
        return audioPlayer.volume
    }

    override fun onTrackEnded(player: String, track: Track) {}
    override fun onTrackPaused(player: String, track: Track) {}
    override fun onTrackResumed(player: String, track: Track) {}
    override fun onTrackStarted(player: String, track: Track) {}
    override fun onTrackStopped(player: String, track: Track) {}
    override fun onAdPlaying() {}
}
