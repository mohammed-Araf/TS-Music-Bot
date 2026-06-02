package ts3musicbot.client

import com.github.manevolent.ts3j.audio.Microphone
import com.github.manevolent.ts3j.enums.CodecType
import com.sedmelluq.discord.lavaplayer.player.AudioPlayer
import com.sedmelluq.discord.lavaplayer.track.playback.MutableAudioFrame
import com.sedmelluq.discord.lavaplayer.format.StandardAudioDataFormats
import com.sedmelluq.discord.lavaplayer.natives.opus.OpusEncoder
import java.nio.ByteBuffer
import java.nio.ByteOrder

class TSAudioProvider(private val audioPlayer: AudioPlayer) : Microphone {
    // Allocate direct buffers as required by the native JNI Opus library
    private val pcmBuffer = ByteBuffer.allocateDirect(StandardAudioDataFormats.COMMON_PCM_S16_LE.maximumChunkSize()).order(ByteOrder.nativeOrder())
    private val frame = MutableAudioFrame()
    private val opusEncoder = OpusEncoder(48000, 2, 10)
    private val opusBuffer = ByteBuffer.allocateDirect(2048)
    private var isMuted = false

    init {
        frame.setBuffer(pcmBuffer)
    }

    override fun getCodec(): CodecType {
        return CodecType.OPUS_MUSIC
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

    override fun provide(): ByteArray? {
        pcmBuffer.clear()
        if (audioPlayer.provide(frame)) {
            val length = frame.dataLength
            if (length > 0) {
                pcmBuffer.position(0)
                pcmBuffer.limit(length)
                
                val shortBuf = pcmBuffer.asShortBuffer()
                val samplesPerChannel = length / 2 / 2 // 2 bytes per sample, 2 channels
                
                opusBuffer.clear()
                val encodedLength = opusEncoder.encode(shortBuf, samplesPerChannel, opusBuffer)
                if (encodedLength > 0) {
                    val opusData = ByteArray(encodedLength)
                    opusBuffer.position(0)
                    opusBuffer.limit(encodedLength)
                    opusBuffer.get(opusData)
                    return opusData
                }
            }
        }
        return ByteArray(0)
    }
}

