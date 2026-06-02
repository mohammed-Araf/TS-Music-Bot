package ts3musicbot.util

interface PlayStateListener {
    fun onTrackEnded(player: String, track: Track)
    fun onTrackPaused(player: String, track: Track)
    fun onTrackResumed(player: String, track: Track)
    fun onTrackStarted(player: String, track: Track)
    fun onTrackStopped(player: String, track: Track)
    fun onAdPlaying()
}
