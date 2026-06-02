package ts3musicbot.client

import com.github.manevolent.ts3j.audio.Microphone
import com.github.manevolent.ts3j.enums.CodecType
import com.sedmelluq.discord.lavaplayer.player.AudioPlayer
import com.sedmelluq.discord.lavaplayer.track.playback.MutableAudioFrame
import com.sedmelluq.discord.lavaplayer.format.StandardAudioDataFormats
import com.sedmelluq.discord.lavaplayer.natives.opus.OpusEncoder
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.ShortBuffer

class TSAudioProvider(private val audioPlayer: AudioPlayer) : Microphone {
    // LavaPlayer produces stereo PCM (DISCORD_PCM_S16_LE: 48kHz, 2ch, S16LE)
    private val pcmBuffer = ByteBuffer.allocateDirect(StandardAudioDataFormats.DISCORD_PCM_S16_LE.maximumChunkSize()).order(ByteOrder.nativeOrder())
    private val frame = MutableAudioFrame()

    // Mono Opus encoder: 48kHz, 1 channel, quality=10 (best)
    // TeamSpeak channels default to OPUS_VOICE which expects mono.
    // Sending stereo Opus to a mono-expecting client causes half-speed playback.
    private val opusEncoder = OpusEncoder(48000, 1, 10)
    private val opusBuffer = ByteBuffer.allocateDirect(2048)

    // Direct buffer for mono PCM (960 samples * 2 bytes = 1920 bytes for 20ms at 48kHz mono)
    private val monoBuffer = ByteBuffer.allocateDirect(960 * 2).order(ByteOrder.nativeOrder())

    private var isMuted = false

    private var provideCount = 0
    private var successCount = 0
    private var emptyCount = 0

    init {
        frame.setBuffer(pcmBuffer)
        frame.setFormat(StandardAudioDataFormats.DISCORD_PCM_S16_LE)
    }

    override fun getCodec(): CodecType {
        // Use OPUS_VOICE (mono) to match standard TS3 channel codec settings
        return CodecType.OPUS_VOICE
    }

    override fun isMuted(): Boolean {
        return isMuted || audioPlayer.isPaused
    }

    fun setMuted(muted: Boolean) {
        this.isMuted = muted
    }

    override fun isReady(): Boolean {
        return audioPlayer.playingTrack != null && !isMuted()
    }

    private var lastTickTime = 0L

    override fun provide(): ByteArray? {
        provideCount++
        pcmBuffer.clear()
        if (audioPlayer.provide(frame)) {
            val length = frame.dataLength
            if (length > 0) {
                successCount++
                // LavaPlayer gives us stereo: length / 2 bytes-per-sample / 2 channels = samples per channel
                val stereoSamplesPerChannel = length / 2 / 2  // = 960 for 20ms at 48kHz

                if (provideCount % 100 == 0) {
                    val now = System.currentTimeMillis()
                    val diff = if (lastTickTime == 0L) 0 else (now - lastTickTime)
                    lastTickTime = now
                    println("[TSAudioProvider] Ticks: $provideCount | Success: $successCount | Empty: $emptyCount | Time for 100 ticks: ${diff}ms | Frame len: $length | Mono samples: $stereoSamplesPerChannel")
                }

                // Downmix stereo to mono: average left and right channels
                pcmBuffer.position(0)
                pcmBuffer.limit(length)
                val stereoShorts = pcmBuffer.asShortBuffer()

                monoBuffer.clear()
                val monoShorts = monoBuffer.asShortBuffer()

                for (i in 0 until stereoSamplesPerChannel) {
                    val left = stereoShorts.get(i * 2).toInt()
                    val right = stereoShorts.get(i * 2 + 1).toInt()
                    val mono = ((left + right) / 2).toShort()
                    monoShorts.put(i, mono)
                }

                monoBuffer.position(0)
                monoBuffer.limit(stereoSamplesPerChannel * 2)  // bytes
                val monoShortView = monoBuffer.asShortBuffer()

                // Encode mono PCM to Opus (samplesPerChannel = 960 for mono)
                opusBuffer.clear()
                val encodedLength = opusEncoder.encode(monoShortView, stereoSamplesPerChannel, opusBuffer)
                if (encodedLength > 0) {
                    val opusData = ByteArray(encodedLength)
                    opusBuffer.position(0)
                    opusBuffer.limit(encodedLength)
                    opusBuffer.get(opusData)
                    return opusData
                }
            } else {
                emptyCount++
            }
        } else {
            emptyCount++
        }
        if (provideCount % 100 == 0) {
            val now = System.currentTimeMillis()
            val diff = if (lastTickTime == 0L) 0 else (now - lastTickTime)
            lastTickTime = now
            println("[TSAudioProvider] Ticks: $provideCount | Success: $successCount | Empty: $emptyCount | Time for 100 ticks: ${diff}ms")
        }
        return ByteArray(0)
    }
}


