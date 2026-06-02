package ts3musicbot.services

import kotlinx.coroutines.Dispatchers.IO
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import ts3musicbot.util.Album
import ts3musicbot.util.Albums
import ts3musicbot.util.Artist
import ts3musicbot.util.Artists
import ts3musicbot.util.Description
import ts3musicbot.util.Discover
import ts3musicbot.util.Discoveries
import ts3musicbot.util.ExtraProperties
import ts3musicbot.util.Genres
import ts3musicbot.util.HTTP_TOO_MANY_REQUESTS
import ts3musicbot.util.Link
import ts3musicbot.util.LinkType
import ts3musicbot.util.Name
import ts3musicbot.util.Playability
import ts3musicbot.util.Playable
import ts3musicbot.util.PostData
import ts3musicbot.util.Publisher
import ts3musicbot.util.ReleaseDate
import ts3musicbot.util.RequestMethod
import ts3musicbot.util.Response
import ts3musicbot.util.SearchQuery
import ts3musicbot.util.SearchResult
import ts3musicbot.util.SearchResults
import ts3musicbot.util.SearchType
import ts3musicbot.util.Show
import ts3musicbot.util.Track
import ts3musicbot.util.TrackList
import ts3musicbot.util.sendHttpRequest
import java.net.HttpURLConnection
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import kotlin.time.Duration.Companion.seconds

class Bandcamp : Service(ServiceType.BANDCAMP) {
    private val formatter = DateTimeFormatter.ofPattern("dd MMM yyyy HH:mm:ss z")

    override fun getSupportedSearchTypes() =
        listOf(
            LinkType.TRACK,
            LinkType.ALBUM,
            LinkType.ARTIST,
        )

    override suspend fun search(
        searchType: SearchType,
        searchQuery: SearchQuery,
        resultLimit: Int,
        encodeQuery: Boolean,
    ): SearchResults {
        val linkBuilder = StringBuilder()
        linkBuilder.append("https://bandcamp.com/api/fuzzysearch/1/app_autocomplete?")
        linkBuilder.append("q=" + if (encodeQuery) encode(searchQuery.query) else searchQuery)
        val response = sendHttpRequest(Link(linkBuilder.toString()))
        lateinit var searchResults: SearchResults
        while (true) {
            when (response.code.code) {
                HttpURLConnection.HTTP_OK -> {
                    val results = JSONObject(response.data.data).getJSONArray("results")
                        .map { item ->
                            item as JSONObject
                            when (item.getString("type")) {
                                "a" -> { //album
                                    val artistName = item.getString("band_name")
                                    val url = item.getString("url")
                                    val artistUrl = url.substringBeforeLast("https://")
                                    val albumUrl = "https://" + url.substringAfterLast("https://")
                                    val albumName = item.getString("name")
                                    val album = Album(
                                        Name(albumName),
                                        Artists(listOf(
                                            Artist(
                                                Name(artistName),
                                                Link(artistUrl)
                                            )
                                        )),
                                        link = Link(albumUrl)
                                    )
                                    SearchResult(album, album.link)
                                }
                                "b" -> {
                                    val artistName = item.getString("name")
                                    val artistUrl = item.getString("url")
                                    val genres = if (!item.isNull("tag_names")) item.getJSONArray("tag_names").map { it as String; it } else emptyList()
                                    val artist = Artist(
                                        Name(artistName),
                                        Link(artistUrl),
                                        genres = Genres(genres)
                                    )
                                    SearchResult(artist, artist.link)
                                }
                                "t" -> {
                                    val album = if (!item.isNull("album_name")) {
                                        Album(Name(item.getString("album_name")))
                                    } else {
                                        Album()
                                    }
                                    val artistName = item.getString("band_name")
                                    val trackTitle = item.getString("name")
                                    val url = item.getString("url")
                                    val artistUrl = url.substringBeforeLast("https://")
                                    val trackUrl = "https://" + url.substringAfterLast("https://")
                                    val artists = Artists(listOf(
                                        Artist(
                                            Name(artistName),
                                            Link(artistUrl)
                                        )
                                    ))
                                    val track = Track(
                                        album,
                                        artists,
                                        Name(trackTitle),
                                        Link(trackUrl)
                                    )
                                    SearchResult(track, track.link)
                                }
                                else -> SearchResult(Playable(), Link())
                            }
                        }
                    val filteredResults = results.filter { it.isNotEmpty() && it.link.linkType(this) == searchType.getType()}
                    searchResults = SearchResults(
                        if (resultLimit != 0 && filteredResults.size > resultLimit) {
                            filteredResults.subList(0, resultLimit)
                        } else {
                            filteredResults
                        }
                    )
                    break
                }

                HTTP_TOO_MANY_REQUESTS -> {
                    println("Too many requests! Waiting for ${response.data} seconds.")
                    // wait for given time before next request.
                    delay(response.data.data.toLong().seconds)
                }

                else -> {
                    SearchResults(emptyList())
                    println("HTTP CODE " + response.code.code)
                }
            }
        }
        return searchResults
    }

    override suspend fun fetchTrack(trackLink: Link): Track {
        val request = sendHttpRequest(trackLink)
        lateinit var track: Track
        withContext(IO) {
            while (true) {
                when (request.code.code) {
                    HttpURLConnection.HTTP_OK -> {
                        val lines = request.data.data.lines()
                        val trackData =
                            JSONObject(lines[lines.indexOfFirst { it.contains("<script type=\"application/ld+json\">") } + 1])
                        val artistID =
                            if (trackData.getJSONObject("byArtist").has("@id")) {
                                trackData.getJSONObject("byArtist").getString("@id")
                            } else if (
                                trackData.getJSONObject("inAlbum").has("byArtist") &&
                                trackData.getJSONObject("inAlbum").getJSONObject("byArtist").has("@id")
                            ) {
                                trackData.getJSONObject("inAlbum").getJSONObject("byArtist").getString("@id")
                            } else {
                                trackData.getJSONObject("publisher").getString("@id")
                            }

                        track =
                            if ("$trackLink".contains("https://\\S+\\.bandcamp\\.com/album/\\S+#t[0-9]+$".toRegex())) {
                                val trackItem =
                                    trackData
                                        .getJSONObject("track")
                                        .getJSONArray("itemListElement")
                                        .first {
                                            it as JSONObject
                                            it.getInt("position") == "$trackLink".substringAfter("#t").toInt()
                                        }.let { it as JSONObject }
                                        .getJSONObject("item")
                                Track(
                                    Album(
                                        Name(trackData.getString("name")),
                                        Artists(
                                            listOf(
                                                Artist(
                                                    Name(trackData.getJSONObject("byArtist").getString("name")),
                                                    Link(artistID),
                                                ),
                                            ),
                                        ),
                                        ReleaseDate(LocalDate.parse(trackData.getString("datePublished"), formatter)),
                                        TrackList(),
                                        Link(trackData.getString("@id")),
                                        Genres(trackData.getJSONArray("keywords").map { it as String }),
                                    ),
                                    Artists(
                                        listOf(
                                            Artist(
                                                Name(trackData.getJSONObject("byArtist").getString("name")),
                                                Link(artistID),
                                            ),
                                        ),
                                    ),
                                    Name(trackItem.getString("name")),
                                    Link(trackItem.getString("@id")),
                                    Playability(trackItem.has("duration")),
                                )
                            } else {
                                Track(
                                    Album(
                                        Name(trackData.getJSONObject("inAlbum").getString("name")),
                                        Artists(
                                            listOf(
                                                Artist(
                                                    Name(
                                                        if (trackData.getJSONObject("inAlbum").has("byArtist")) {
                                                            trackData.getJSONObject("inAlbum").getJSONObject("byArtist").getString("name")
                                                        } else {
                                                            trackData.getJSONObject("byArtist").getString("name")
                                                        },
                                                    ),
                                                    Link(artistID),
                                                ),
                                            ),
                                        ),
                                        ReleaseDate(LocalDate.parse(trackData.getString("datePublished"), formatter)),
                                        TrackList(),
                                        Link(trackData.getJSONObject("inAlbum").getString("@id")),
                                        Genres(trackData.getJSONArray("keywords").map { it as String }),
                                    ),
                                    Artists(
                                        listOf(
                                            Artist(
                                                Name(
                                                    if (trackData.getJSONObject("inAlbum").has("byArtist")) {
                                                        trackData.getJSONObject("inAlbum").getJSONObject("byArtist").getString("name")
                                                    } else {
                                                        trackData.getJSONObject("byArtist").getString("name")
                                                    },
                                                ),
                                                Link(artistID),
                                            ),
                                        ),
                                    ),
                                    Name(trackData.getString("name")),
                                    Link(trackData.getString("@id")),
                                    Playability(trackData.has("duration")),
                                )
                            }
                        return@withContext
                    }

                    HTTP_TOO_MANY_REQUESTS -> {
                        println("Too many requests! Waiting for ${request.data} seconds.")
                        // wait for given time before next request.
                        delay(request.data.data.toLong().seconds)
                    }

                    else -> {
                        println("HTTP ERROR! CODE: ${request.code}")
                        track = Track()
                        return@withContext
                    }
                }
            }
        }
        return track
    }

    override suspend fun fetchAlbum(albumLink: Link): Album {
        val request = sendHttpRequest(albumLink)
        return when (request.code.code) {
            HttpURLConnection.HTTP_OK -> {
                val lines = request.data.data.lines()
                val albumData =
                    JSONObject(lines[lines.indexOfFirst { it.contains("<script type=\"application/ld+json\">") } + 1])
                Album(
                    Name(albumData.getString("name")),
                    Artists(
                        listOf(
                            Artist(
                                Name(albumData.getJSONObject("byArtist").getString("name")),
                                Link(albumData.getString("@id").substringBefore("/album")),
                            ),
                        ),
                    ),
                    ReleaseDate(LocalDate.parse(albumData.getString("datePublished"), formatter)),
                    fetchAlbumTracks(albumLink),
                    Link(albumData.getString("@id")),
                    Genres(albumData.getJSONArray("keywords").map { it as String }),
                )
            }

            else -> Album()
        }
    }

    override suspend fun fetchAlbumTracks(
        albumLink: Link,
        limit: Int,
    ): TrackList {
        val request = sendHttpRequest(albumLink)
        return when (request.code.code) {
            HttpURLConnection.HTTP_OK -> {
                val lines = request.data.data.lines()
                val albumData =
                    JSONObject(lines[lines.indexOfFirst { it.contains("<script type=\"application/ld+json\">") } + 1])
                TrackList(
                    albumData
                        .getJSONObject("track")
                        .getJSONArray("itemListElement")
                        .map {
                            it as JSONObject
                            val trackData = it.getJSONObject("item")
                            Track(
                                Album(
                                    Name(albumData.getString("name")),
                                    Artists(
                                        listOf(
                                            Artist(
                                                Name(albumData.getJSONObject("byArtist").getString("name")),
                                                Link(albumData.getString("@id").substringBefore("/album")),
                                            ),
                                        ),
                                    ),
                                    ReleaseDate(LocalDate.parse(albumData.getString("datePublished"), formatter)),
                                    link = Link(albumData.getString("@id")),
                                ),
                                Artists(
                                    listOf(
                                        Artist(
                                            Name(albumData.getJSONObject("byArtist").getString("name")),
                                            Link(albumData.getString("@id").substringBefore("/album")),
                                        ),
                                    ),
                                ),
                                Name(trackData.getString("name")),
                                Link(trackData.getString("@id")),
                                Playability(trackData.has("duration")),
                            )
                        }.let { list ->
                            if (limit != 0 && list.size > limit) {
                                list.subList(0, limit)
                            } else {
                                list
                            }
                        },
                )
            }

            else -> TrackList()
        }
    }

    override suspend fun fetchArtist(
        artistLink: Link,
        fetchRecommendations: Boolean,
    ): Artist {
        val request = sendHttpRequest(artistLink)
        return when (request.code.code) {
            HttpURLConnection.HTTP_OK -> {
                val lines = request.data.data.lines()
                var name = Name()
                val link = Link(artistLink.link.replace("\\.com.*".toRegex(), ".com"))
                val topTracks = ArrayList<Track>()
                val relatedArtists =
                    if (fetchRecommendations) {
                        fetchRecommendedArtists(
                            Link(
                                "https://bandcamp.com/recommended/${
                                    link.link.replace("(^https://|\\.bandcamp\\.com.*$)".toRegex(), "")
                                }",
                            ),
                        )
                    } else {
                        Artists()
                    }
                val albums = ArrayList<Album>()

                for (line in lines) {
                    when {
                        line.contains("<meta property=\"og:site_name\"") -> {
                            name = Name(line.substringAfter("content=\"").substringBeforeLast("\">"))
                        }

                        line.contains("href=\"/album/") && fetchRecommendations -> {
                            albums.add(
                                fetchAlbum(
                                    Link(
                                        "$link/album/" +
                                            line
                                                .substringAfter("/album/")
                                                .substringBeforeLast("\">"),
                                    ),
                                ),
                            )
                        }
                    }
                }

                // Since bandcamp has no such thing as top tracks, just pick (up to) 10 tracks from the albums
                for (album in albums) {
                    for (track in album.tracks.trackList) {
                        if (topTracks.size < 10) {
                            topTracks.add(track)
                        } else {
                            break
                        }
                    }
                }

                Artist(name, link, TrackList(topTracks), relatedArtists, albums = Albums(albums))
            }

            else -> Artist()
        }
    }

    suspend fun fetchDiscover(discoverLink: Link): Discoveries {
        var format = "digital"
        var sorting = "top"
        var country = 0
        var subGenre = ""
        lateinit var genres: List<String>
        lateinit var response: Response
        if ("$discoverLink".contains("bandcamp.com/discover/\\S+(/\\S+)?".toRegex())) {
            val postJSON = JSONObject()
            genres = "$discoverLink".substringAfter("discover/").substringBefore('/').split('+').ifEmpty { emptyList() }
            country =
                if ("$discoverLink".contains("loc=[0-9]+".toRegex())) {
                    "$discoverLink".substringAfter("loc=").substringBefore('&').toInt()
                } else {
                    0
                }
            if ("$discoverLink".contains("s=\\w+".toRegex())) {
                sorting = "$discoverLink".substringAfter("s=").substringBefore('&')
            }
            format = "$discoverLink".substringAfter(genres.joinToString("+")).replace("/", "").substringBefore('?')
            val formats =
                mapOf(
                    Pair("", 0),
                    Pair("digital", 1),
                    Pair("vinyl", 2),
                    Pair("cd", 3),
                    Pair("cassette", 4),
                    Pair("tshirt", 5),
                )
            if (format != "digital") {
                println("Non digital formats are unsupported! Changing to digital...")
                format = "digital"
            }
            postJSON.put("category_id", formats[format])
            postJSON.put("geoname_id", country)
            postJSON.put("slice", sorting)
            postJSON.put("tag_norm_names", genres)
            postJSON.put("include_result_types", listOf("a"))
            val link = Link("https://bandcamp.com/api/discover/1/discover_web")
            val extraProperties = ExtraProperties(mapOf(Pair("Content-Type", "application/json")))
            val postData = PostData(listOf(postJSON.toString()))
            response = sendHttpRequest(link, RequestMethod.POST, extraProperties, postData)
        } else {
            val linkBuilder = StringBuilder()
            genres = listOf("all")
            var page = 0
            for (part in discoverLink.link
                .replace("^.*/".toRegex(), "")
                .replace("#?discover$?".toRegex(), "")
                .split("[?&]".toRegex())) {
                val value = part.substringAfter('=')
                when (part.substringBefore('=')) {
                    "g" -> genres = listOf(value.ifEmpty { "all" })
                    "t" -> subGenre = value
                    "s" -> sorting = value
                    "p" -> page = value.toInt()
                    "f" -> format = value
                    "gn" -> country = value.toInt()
                }
            }
            if (format != "digital") {
                println("Non digital formats are unsupported! Changing to digital...")
                format = "digital"
            }
            linkBuilder.append("https://bandcamp.com/api/discover/3/get_web?")
            linkBuilder.append("f=$format")
            linkBuilder.append("&g=" + genres.first())
            if (subGenre.isNotEmpty()) linkBuilder.append("&t=$subGenre")
            linkBuilder.append("&s=$sorting")
            linkBuilder.append("&p=$page")
            linkBuilder.append("&gn=$country")
            response = sendHttpRequest(Link(linkBuilder.toString()))
        }

        suspend fun parseDiscoverItems(data: JSONArray): Discoveries {
            val discoveries = ArrayList<Discover>()
            val albums = ArrayList<Album>()
            for (item in data) {
                item as JSONObject
                when (item.getString("result_type")) {
                    "a" -> {
                        val itemLink = Link(item.getString("item_url").substringBefore('?'))
                        albums.add(fetchAlbum(itemLink))
                    }
                }
            }
            discoveries.add(
                Discover(
                    Name(
                        "Discover" +
                            when (genres.size) {
                                0 -> ""
                                1 -> " " + genres.first()
                                2 -> " " + genres.first() + " and " + genres.last()
                                else -> " " + genres.subList(0, genres.size - 2).joinToString(", ") + " and " + genres.last()
                            },
                    ),
                    Albums(albums),
                    link = discoverLink,
                    useCustomName = true,
                ),
            )
            return Discoveries(discoveries)
        }

        suspend fun parseDiscover3Items(data: JSONArray): Discoveries {
            val discoveries = ArrayList<Discover>()
            val albums = ArrayList<Album>()
            for (item in data) {
                item as JSONObject
                when (item.getString("type")) {
                    "a" -> {
                        val urlHints = item.getJSONObject("url_hints")
                        val subDomain = urlHints.getString("subdomain")
                        val slug = urlHints.getString("slug")

                        albums.add(
                            fetchAlbum(Link("https://$subDomain.bandcamp.com/album/$slug")),
                        )
                    }
                }
            }
            discoveries.add(
                Discover(
                    Name("Discover " + genres.first() + if (subGenre.isNotEmpty()) "/$subGenre" else ""),
                    Albums(albums),
                    link = discoverLink,
                    useCustomName = true,
                ),
            )
            return Discoveries(discoveries)
        }

        return when (response.code.code) {
            HttpURLConnection.HTTP_OK -> {
                try {
                    val data = JSONObject(response.data.data)
                    when {
                        data.has("results") -> parseDiscoverItems(data.getJSONArray("results"))
                        data.has("items") -> parseDiscover3Items(data.getJSONArray("items"))
                        else -> Discoveries()
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                    println("Failed JSON:\n${response.data}\n")
                    Discoveries()
                }
            }

            else -> Discoveries()
        }
    }

    /**
     * Fetch recommended artists for the given artist link
     * @param recommendationsLink Link to get recommendations from
     */
    private suspend fun fetchRecommendedArtists(recommendationsLink: Link): Artists {
        val response = sendHttpRequest(recommendationsLink)

        return when (response.code.code) {
            HttpURLConnection.HTTP_OK -> {
                Artists(
                    response.data.data
                        .lines()
                        .filter { it.contains("href=\"https://\\S+\\.bandcamp\\.com/album/\\S+".toRegex()) }
                        .map { Link("https://" + it.substringAfter("href=\"https://").substringBefore('/')) }
                        .distinct()
                        .map { fetchArtist(it, false) },
                )
            }

            else -> Artists()
        }
    }

    suspend fun fetchRecommendedAlbums(recommendationsLink: Link): Albums {
        val response = sendHttpRequest(recommendationsLink)

        return when (response.code.code) {
            HttpURLConnection.HTTP_OK -> {
                Albums(
                    response.data.data
                        .lines()
                        .filter { it.contains("href=\"https://\\S+\\.bandcamp\\.com/album/\\S+".toRegex()) }
                        .map { fetchAlbum(Link(it.substringAfter("href=\"").substringBefore('?'))) },
                )
            }

            else -> Albums()
        }
    }

    suspend fun fetchShow(showLink: Link): Show {
        val showId = "$showLink".substringAfter("show=").substringBefore("&").toInt()

        fun fetchShowData(): Response {
            val link = Link("https://bandcamp.com/api/bcradio_api/1/get_show")
            val extraProperties = ExtraProperties(mapOf(Pair("Content-Type", "application/json")))
            val postJSON = JSONObject()
            postJSON.put("id", showId)
            return sendHttpRequest(
                link,
                RequestMethod.POST,
                extraProperties,
                PostData(listOf(postJSON.toString())),
            )
        }
        val websiteResponse = sendHttpRequest(showLink)
        val apiResponse = fetchShowData()

        fun parseShowData(
            websiteJSON: JSONObject?,
            apiJSON: JSONObject?,
        ): Show {
            return if (websiteJSON != null && apiJSON != null) {
                val websiteShowData =
                    websiteJSON.getJSONObject("appData").getJSONArray("shows").first {
                        it as JSONObject
                        it.getInt("itemId") == showId
                    } as JSONObject
                val title = apiJSON.getString("title")
                val imageCaption = websiteShowData.getString("metadata")
                val publisher =
                    Publisher(
                        Name(imageCaption.substringAfter(">").substringBefore("<")),
                        Link(imageCaption.substringAfter("href=\"").substringBefore("\"")),
                    )
                val tracksData = apiJSON.getJSONArray("tracks")
                Show(
                    Name(title),
                    publisher,
                    // TODO: get release date
                    description = Description(websiteShowData.getString("description"), websiteShowData.getString("shortDesc")),
                    episodeName = Name(apiJSON.getString("title")),
                    tracks =
                        TrackList(
                            tracksData.map { track ->
                                track as JSONObject
                                val trackLink = Link(track.getString("url"))
                                val artists =
                                    Artists(
                                        listOf(
                                            Artist(
                                                Name(track.getString("artistName")),
                                                Link(track.getString("bandUrl")),
                                            ),
                                        ),
                                    )
                                val albumData = track.getJSONObject("album")
                                Track(
                                    Album(
                                        Name(albumData.getString("title")),
                                        artists,
                                        link = Link(albumData.getString("url")),
                                    ),
                                    artists,
                                    Name(track.getString("title")),
                                    trackLink,
                                    Playability(websiteShowData.getBoolean("isPublished")),
                                )
                            },
                        ),
                )
            } else {
                Show()
            }
        }

        var websiteJSON: JSONObject? = null
        var apiJSON: JSONObject? = null
        withContext(IO) {
            when (websiteResponse.code.code) {
                HttpURLConnection.HTTP_OK -> {
                    try {
                        val html = websiteResponse.data.data
                        websiteJSON =
                            JSONObject(
                                decode(
                                    html.substringAfter("data-blob=\"")
                                        .substringBefore("\">"),
                                ),
                            )
                    } catch (e: Exception) {
                        println(e)
                        println("Failed JSON:\n${websiteResponse.data}\n")
                        this.cancel()
                        return@withContext
                    }
                }

                else -> {
                    this.cancel()
                    return@withContext
                }
            }
            when (val code = apiResponse.code.code) {
                HttpURLConnection.HTTP_OK -> {
                    try {
                        apiJSON = JSONObject(apiResponse.data.data)
                    } catch (e: Exception) {
                        e.printStackTrace()
                        val msg = "Failed JSON:\n${apiResponse.data}\n"
                        println(msg)
                        this.cancel(msg)
                        return@withContext
                    }
                }

                else -> {
                    this.cancel("Got error code $code")
                    return@withContext
                }
            }
        }
        return parseShowData(websiteJSON, apiJSON)
    }

    override suspend fun resolveType(link: Link): LinkType =
        when {
            "$link".contains("https?://\\S+\\.bandcamp\\.com/(track/\\S+|album/\\S+#t[0-9]+$)".toRegex()) -> LinkType.TRACK
            "$link".contains("https?://\\S+\\.bandcamp\\.com/album/\\S+".toRegex()) -> LinkType.ALBUM
            "$link".contains("https?://bandcamp\\.com/recommended/\\S+".toRegex()) -> LinkType.RECOMMENDED
            "$link".contains("https?://\\S+\\.bandcamp\\.com(/(music|merch|community))?$".toRegex()) -> LinkType.ARTIST
            "$link".contains("https?://bandcamp\\.com/(discover\\S*|\\S*#discover$)".toRegex()) -> LinkType.DISCOVER
            "$link".contains("https?://bandcamp\\.com/?\\?show=\\S+".toRegex()) -> LinkType.SHOW
            else -> LinkType.OTHER
        }
}
