import { useState, useRef, useCallback } from 'react'

export default function useAudio() {
  const [isAudioOn, setIsAudioOn] = useState(true)
  const audioQueueRef = useRef([])
  const currentAudioRef = useRef(null)
  const currentUrlRef = useRef(null)
  const isAudioOnRef = useRef(true)

  const playNext = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      return
    }

    const base64 = audioQueueRef.current.shift()
    const binaryString = atob(base64)
    const bytes = new Uint8Array(binaryString.length)
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }
    const blob = new Blob([bytes], { type: 'audio/mpeg' })
    const url = URL.createObjectURL(blob)

    const audio = new Audio(url)
    currentAudioRef.current = audio
    currentUrlRef.current = url

    audio.onended = () => {
      URL.revokeObjectURL(url)
      currentAudioRef.current = null
      currentUrlRef.current = null
      playNext()
    }

    audio.onerror = () => {
      URL.revokeObjectURL(url)
      currentAudioRef.current = null
      currentUrlRef.current = null
      playNext()
    }

    audio.play().catch(() => {
      URL.revokeObjectURL(url)
      currentAudioRef.current = null
      currentUrlRef.current = null
      playNext()
    })
  }, [])

  const queueAudioChunk = useCallback((base64) => {
    if (!isAudioOnRef.current) return

    audioQueueRef.current.push(base64)

    if (!currentAudioRef.current) {
      playNext()
    }
  }, [playNext])

  const clearQueue = useCallback(() => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause()
      currentAudioRef.current.onended = null
      currentAudioRef.current.onerror = null
      currentAudioRef.current = null
    }
    if (currentUrlRef.current) {
      URL.revokeObjectURL(currentUrlRef.current)
      currentUrlRef.current = null
    }
    audioQueueRef.current = []
  }, [])

  const toggleAudio = useCallback(() => {
    setIsAudioOn(prev => {
      const next = !prev
      isAudioOnRef.current = next
      if (!next) {
        clearQueue()
      }
      return next
    })
  }, [clearQueue])

  return {
    isAudioOn,
    toggleAudio,
    queueAudioChunk,
    clearQueue,
  }
}
