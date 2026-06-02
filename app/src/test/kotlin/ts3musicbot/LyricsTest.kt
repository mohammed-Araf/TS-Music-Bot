package ts3musicbot

import kotlinx.coroutines.Dispatchers.IO
import kotlinx.coroutines.runBlocking
import ts3musicbot.services.Spotify
import ts3musicbot.services.YouTube
import ts3musicbot.services.Bandcamp
import ts3musicbot.services.SoundCloud
import ts3musicbot.services.Lyrics
import ts3musicbot.util.BotSettings
import ts3musicbot.util.Link
import ts3musicbot.util.Name
import ts3musicbot.util.Track
import kotlin.test.Test
import kotlin.test.assertFalse
import java.util.Base64

class LyricsTest {
    // Setup spotify
    private val lyrics = Lyrics()
    private val spotifyMarket = "US"
    private val key =
    String(
        Base64.getEncoder().encode(
            (
                "KIDO0ETZkZjY0UTY4QGM4gjY2MDNkdTN2EWZzADNkBDZ" + ":" +
                "KUGMwUWYyADZhdTYmRmMjFWOwgDN1IjMwUWN1M2YyQTZ"
            ).split(":").reversed().joinToString(":") {
                String(Base64.getDecoder().decode(it.reversed())).trim()
            }.toByteArray(),
        ),
    )
    private val botSettings = BotSettings(market = spotifyMarket, spApiKey = key)
    private val spotify = Spotify(botSettings).also { runBlocking(IO) { it.updateToken() } }

    // Setup Bandcamp
    private val bandcamp = Bandcamp()

    // Setup Soundcloud
    private val soundcloud = SoundCloud()

    // Setup Youtube
    private val ytKey = "gCBlkehNVeC9lRwpEVZZVT1FlMJ9FR4FWakhVVkdje0EVLTNWT2ZTW"
    private val youTube = YouTube(String(Base64.getDecoder().decode("${"=".repeat(2)}$ytKey".reversed().trim())).reversed().trim())

    @Test
    fun testGettingLyricsForSpotifyTracks() {
        runBlocking(IO) {
            val trackLink = Link("https://open.spotify.com/track/4UEo1b0wWrtHMC8bVqPiH8")
            val track = spotify.fetchTrack(trackLink)

            assertFalse(
                lyrics.getLyrics(track) ==
                listOf("Couldn't find lyrics for track: ${track.toShortString()}")
            )
        }
    }

    @Test
    fun testGettingLyricsForYoutubeTracks() {
        runBlocking(IO) {
            val trackLink = Link("https://youtu.be/AP55-ysy6xo")
            val track = youTube.fetchVideo(trackLink)

            assertFalse(
                lyrics.getLyrics(track) ==
                listOf("Couldn't find lyrics for track: ${track.toShortString()}")
            )
        }
    }

    @Test
    fun testGettingLyricsForSoundcloudTracks() {
        runBlocking(IO) {
            val trackLink = Link("https://soundcloud.com/edsheeran/shape-of-you")
            val track = soundcloud.fetchTrack(trackLink)

            assertFalse(
                lyrics.getLyrics(track) ==
                listOf("Couldn't find lyrics for track: ${track.toShortString()}")
            )
        }
    }
}
