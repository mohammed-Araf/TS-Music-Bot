package ts3musicbot.services

import ts3musicbot.util.Track
import ts3musicbot.util.Link
import ts3musicbot.services.Service
import ts3musicbot.util.sendHttpRequest
import org.json.JSONString
import org.json.JSONObject

class Lyrics : Service(ServiceType.OTHER) {
    fun getLyrics(track: Track): List<String> {
        val baseUrl = "https://api.lyrics.ovh/v1"
        var trackTitle = ""
        var trackArtists = ""

        val actualArtists = track.artists.artists.map {artist -> artist.name.name.lowercase().replace("- topic", "").trim()}.joinToString(separator = ",")
        when (track.link.serviceType()) {
            ServiceType.YOUTUBE, ServiceType.SOUNDCLOUD -> {
                val tempTitle = track.title.name.lowercase().replace("([\\[(*](.*video|.*audio|.*visualizer|official.*|h(d|q)|.*\\d{3,4}.*|.*demo.*|single|4k.*|.*hd|cover.*|vocals.*|h(q|d)|cd|lq| cut|.*cover.*|live.*|.*track|reaction.*|reupload|.*quality|vocal|instrumental|multi-angle|free (download|dl)|pro-shot|review|.*version|.*only|.*playthrough|explicit|.*one-take|)[\\])*]|.*lyric.*|ft\\..*|feat\\..*)".toRegex(), "")
                if (tempTitle.trim().contains("(-|–|\\|)".toRegex())) {
                    val parts = tempTitle.split("(-|–|\\|)".toRegex()).map {it -> it.trim().lowercase()}
                    if (parts[1].contains(actualArtists.lowercase())) {
                        trackTitle = parts[0]
                        trackArtists = parts[1]
                    } else {
                        trackTitle = parts[1]
                        trackArtists = parts[0]
                    }
                } else {
                    trackTitle = track.title.name
                    trackArtists = actualArtists
                }
            }
            else -> {
                trackTitle = track.title.name
                trackArtists = actualArtists
            }
        }
        val url = "$baseUrl/${encode(trackArtists.trim())}/${encode(trackTitle.trim())}"
        if (trackTitle.isEmpty()) {
            return listOf("No track is playing!")
        } else {
            val result = sendHttpRequest(
                Link(url)
            )
            if (result.code.code != 200) {
                return listOf("Couldn't find lyrics for track: ${track.toShortString()}")
            } else {
                return listOf("Showing lyrics for track: ${track.toShortString()}", JSONObject(result.data.data).getString("lyrics"))
            }
        }
    }
}
