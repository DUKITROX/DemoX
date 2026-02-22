import { useState, useRef, useCallback, useEffect } from 'react'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

function buildApiUrl(path) {
  return `${API_BASE_URL}${path}`
}

function extractSseData(eventBlock) {
  const dataLines = eventBlock
    .split('\n')
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trimStart())

  if (dataLines.length === 0) {
    return null
  }

  return dataLines.join('\n')
}

export default function useChat({ onAudioChunk, targetUrl } = {}) {
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [latestScreenshot, setLatestScreenshot] = useState(null)
  const [cursorPos, setCursorPos] = useState(null)
  const sessionId = useRef('session_' + Math.random().toString(36).substring(2, 9))
  const nextId = useRef(1)
  const activeRequestIdRef = useRef(0)
  const abortControllerRef = useRef(null)

  const createMessageId = () => {
    nextId.current += 1
    return Date.now() + nextId.current
  }

  const fetchInitialScreenshot = useCallback(async () => {
    try {
      const res = await fetch(buildApiUrl('/screenshot'))
      const data = await res.json()
      if (data.screenshot) {
        setLatestScreenshot('data:image/jpeg;base64,' + data.screenshot)
      }
    } catch {
      // Backend not available yet
    }
  }, [])

  const sendMessage = useCallback(async (text) => {
    if (!text.trim()) return

    // Interrupt the active stream if user sends a new message mid-response.
    if (abortControllerRef.current && isLoading) {
      // Mark the current bot message as interrupted before aborting
      setMessages(prev => {
        const updated = [...prev]
        for (let i = updated.length - 1; i >= 0; i--) {
          if (updated[i].type === 'bot' && updated[i].content) {
            updated[i] = {
              ...updated[i],
              interrupted: true,
            }
            break
          }
        }
        return updated
      })
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    } else if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    const requestId = Date.now() + Math.floor(Math.random() * 100000)
    activeRequestIdRef.current = requestId
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    const userMsg = { id: createMessageId(), type: 'user', content: text }
    setIsLoading(true)

    const botMsgId = createMessageId()
    setMessages(prev => [...prev, userMsg, { id: botMsgId, type: 'bot', content: '' }])

    try {
      const response = await fetch(buildApiUrl('/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortController.signal,
        body: JSON.stringify({
          message: text,
          session_id: sessionId.current,
          url: targetUrl || undefined,
        }),
      })

      if (!response.ok || !response.body) {
        throw new Error(`Chat request failed with status ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let shouldStop = false

      while (!shouldStop) {
        const { value, done } = await reader.read()
        if (done) {
          break
        }

        if (activeRequestIdRef.current !== requestId) {
          shouldStop = true
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''

        for (const eventBlock of events) {
          const eventData = extractSseData(eventBlock)
          if (!eventData) continue

          try {
            const data = JSON.parse(eventData)

            if (data.type === 'token') {
              setMessages(prev =>
                prev.map(m =>
                  m.id === botMsgId
                    ? { ...m, content: m.content + data.content }
                    : m
                )
              )
            } else if (data.type === 'screenshot') {
              setLatestScreenshot('data:image/jpeg;base64,' + data.content)
            } else if (data.type === 'cursor_move') {
              setCursorPos({ x: data.x, y: data.y })
            } else if (data.type === 'audio') {
              if (onAudioChunk) {
                onAudioChunk(data.content)
              }
            } else if (data.type === 'end') {
              shouldStop = true
              break
            }
          } catch {
            // Skip malformed chunks
          }
        }
      }
    } catch (err) {
      if (err?.name === 'AbortError') {
        return
      }

      setMessages(prev =>
        prev.map(m =>
          m.id === botMsgId
            ? { ...m, content: 'Error connecting to server.' }
            : m
        )
      )
    } finally {
      setMessages(prev => prev.filter(m => !(m.id === botMsgId && m.content === '')))
      if (activeRequestIdRef.current === requestId) {
        abortControllerRef.current = null
        setIsLoading(false)
      }
    }
  }, [isLoading])

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  const interruptCurrentResponse = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
  }, [])

  return {
    messages,
    sendMessage,
    interruptCurrentResponse,
    isLoading,
    latestScreenshot,
    setLatestScreenshot,
    fetchInitialScreenshot,
    cursorPos,
  }
}
