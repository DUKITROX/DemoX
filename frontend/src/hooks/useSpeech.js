import { useState, useRef, useCallback, useEffect } from 'react'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

// VAD configuration
const VAD_THRESHOLD = 0.015        // RMS energy threshold to detect speech
const SILENCE_DURATION_MS = 1500   // How long silence before we consider speech ended
const VAD_CHECK_INTERVAL_MS = 50   // How often to check audio levels

/**
 * useSpeech hook with:
 * - Web Audio API AnalyserNode for voice activity detection (VAD)
 * - MediaRecorder for audio capture
 * - ElevenLabs STT via backend /transcribe endpoint
 *
 * @param {Object} options
 * @param {Function} options.onSpeechStart - Called immediately when user starts talking (for barge-in)
 * @param {Function} options.onTranscript  - Called with transcript text when speech ends and is transcribed
 */
export default function useSpeech({ onSpeechStart, onTranscript } = {}) {
  const [isListening, setIsListening] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)

  const micStreamRef = useRef(null)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const vadIntervalRef = useRef(null)
  const chunksRef = useRef([])
  const isSpeakingRef = useRef(false)
  const silenceStartRef = useRef(null)
  const onSpeechStartRef = useRef(onSpeechStart)
  const onTranscriptRef = useRef(onTranscript)
  const isListeningRef = useRef(false)

  // Keep refs in sync with latest callbacks
  useEffect(() => { onSpeechStartRef.current = onSpeechStart }, [onSpeechStart])
  useEffect(() => { onTranscriptRef.current = onTranscript }, [onTranscript])

  const getRmsLevel = useCallback(() => {
    const analyser = analyserRef.current
    if (!analyser) return 0
    const data = new Float32Array(analyser.fftSize)
    analyser.getFloatTimeDomainData(data)
    let sum = 0
    for (let i = 0; i < data.length; i++) {
      sum += data[i] * data[i]
    }
    return Math.sqrt(sum / data.length)
  }, [])

  const sendForTranscription = useCallback(async (audioBlob) => {
    if (audioBlob.size < 1000) return // too small, probably silence

    setIsTranscribing(true)
    try {
      const formData = new FormData()
      formData.append('file', audioBlob, 'recording.webm')

      const res = await fetch(`${API_BASE_URL}/transcribe`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        console.warn('[useSpeech] Transcription failed:', res.status)
        return
      }

      const data = await res.json()
      if (data.transcript && onTranscriptRef.current) {
        onTranscriptRef.current(data.transcript)
      }
    } catch (err) {
      console.warn('[useSpeech] Transcription error:', err)
    } finally {
      setIsTranscribing(false)
    }
  }, [])

  const startRecording = useCallback(() => {
    const stream = micStreamRef.current
    if (!stream) return

    chunksRef.current = []

    // Use webm/opus which is well-supported and ElevenLabs accepts
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'

    const recorder = new MediaRecorder(stream, { mimeType })
    mediaRecorderRef.current = recorder

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        chunksRef.current.push(e.data)
      }
    }

    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mimeType })
      chunksRef.current = []
      sendForTranscription(blob)
    }

    recorder.start(100) // collect data every 100ms
  }, [sendForTranscription])

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop()
    }
    mediaRecorderRef.current = null
  }, [])

  const startListening = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      micStreamRef.current = stream
    } catch (err) {
      console.warn('[useSpeech] Microphone access denied:', err)
      return
    }

    // Set up Web Audio API for VAD
    const audioContext = new (window.AudioContext || window.webkitAudioContext)()
    audioContextRef.current = audioContext

    const source = audioContext.createMediaStreamSource(micStreamRef.current)
    const analyser = audioContext.createAnalyser()
    analyser.fftSize = 2048
    source.connect(analyser)
    analyserRef.current = analyser

    isSpeakingRef.current = false
    silenceStartRef.current = null
    isListeningRef.current = true
    setIsListening(true)

    // VAD loop: check audio levels periodically
    vadIntervalRef.current = setInterval(() => {
      if (!isListeningRef.current) return

      const rms = getRmsLevel()
      const isSpeechNow = rms > VAD_THRESHOLD

      if (isSpeechNow) {
        silenceStartRef.current = null

        if (!isSpeakingRef.current) {
          // Speech just started
          isSpeakingRef.current = true
          if (onSpeechStartRef.current) {
            onSpeechStartRef.current()
          }
          startRecording()
        }
      } else if (isSpeakingRef.current) {
        // Was speaking, now silent
        if (!silenceStartRef.current) {
          silenceStartRef.current = Date.now()
        } else if (Date.now() - silenceStartRef.current > SILENCE_DURATION_MS) {
          // Enough silence — speech segment ended
          isSpeakingRef.current = false
          silenceStartRef.current = null
          stopRecording()
        }
      }
    }, VAD_CHECK_INTERVAL_MS)
  }, [getRmsLevel, startRecording, stopRecording])

  const stopListening = useCallback(() => {
    isListeningRef.current = false

    if (vadIntervalRef.current) {
      clearInterval(vadIntervalRef.current)
      vadIntervalRef.current = null
    }

    // If currently recording, stop and transcribe
    if (isSpeakingRef.current) {
      isSpeakingRef.current = false
      stopRecording()
    }

    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {})
      audioContextRef.current = null
    }
    analyserRef.current = null

    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach(t => t.stop())
      micStreamRef.current = null
    }

    setIsListening(false)
  }, [stopRecording])

  const toggleListening = useCallback(() => {
    if (isListening) {
      stopListening()
    } else {
      startListening()
    }
  }, [isListening, startListening, stopListening])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isListeningRef.current = false
      if (vadIntervalRef.current) clearInterval(vadIntervalRef.current)
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
      if (audioContextRef.current) audioContextRef.current.close().catch(() => {})
      if (micStreamRef.current) micStreamRef.current.getTracks().forEach(t => t.stop())
    }
  }, [])

  return { isListening, isTranscribing, toggleListening, isSupported: true }
}
