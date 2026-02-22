import { useEffect, useState, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import ScreenShare from '../components/ScreenShare'
import ChatPanel from '../components/ChatPanel'
import ControlBar from '../components/ControlBar'
import useChat from '../hooks/useChat'
import useSpeech from '../hooks/useSpeech'
import useAudio from '../hooks/useAudio'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export default function Demo() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const targetUrl = searchParams.get('url') || ''
  const [isJoining, setIsJoining] = useState(true)
  const [isChatOpen, setIsChatOpen] = useState(true)
  const [isCameraOn, setIsCameraOn] = useState(false)
  const videoRef = useRef(null)
  const streamRef = useRef(null)

  const {
    isAudioOn,
    toggleAudio,
    queueAudioChunk,
    clearQueue: clearAudioQueue,
  } = useAudio()

  const {
    messages,
    sendMessage,
    interruptCurrentResponse,
    isLoading,
    latestScreenshot,
    setLatestScreenshot,
    cursorPos,
  } = useChat({ onAudioChunk: queueAudioChunk, targetUrl })

  const { isListening, isTranscribing, toggleListening, isSupported: micSupported } = useSpeech({
    onSpeechStart: () => {
      // Immediately stop agent audio when user starts talking (barge-in)
      clearAudioQueue()
      interruptCurrentResponse()
    },
    onTranscript: (transcript) => {
      sendMessage(transcript)
    },
  })

  // Transition out of waiting screen once the agent starts talking
  useEffect(() => {
    if (isJoining && messages.some(m => m.type === 'bot' && m.content)) {
      setIsJoining(false)
    }
  }, [messages, isJoining])

  useEffect(() => {
    const init = async () => {
      if (targetUrl) {
        try {
          const res = await fetch(`${API_BASE_URL}/navigate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: targetUrl }),
          })
          const data = await res.json()
          if (data.screenshot) {
            setLatestScreenshot('data:image/jpeg;base64,' + data.screenshot)
          }
        } catch {
          // Navigate failed, will still try to chat
        }
      }
      sendMessage('Hi')
    }
    init()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Camera management (lifted from ControlBar)
  const toggleCamera = async () => {
    if (isCameraOn) {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop())
        streamRef.current = null
      }
      setIsCameraOn(false)
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true })
        streamRef.current = stream
        setIsCameraOn(true)
      } catch {
        // Camera access denied
      }
    }
  }

  useEffect(() => {
    if (videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current
    }
  }, [isCameraOn])

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop())
      }
    }
  }, [])

  const handleSendMessage = (text) => {
    clearAudioQueue()
    sendMessage(text)
  }

  if (isJoining) {
    return (
      <div className="h-screen bg-gray-50 flex flex-col items-center justify-center relative overflow-hidden">
        <div className="relative z-10 flex flex-col items-center animate-fade-in">
          {/* Animated logo ring */}
          <div className="relative w-28 h-28 mb-8">
            <div className="absolute inset-0 rounded-full border-2 border-mint-light" />
            <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-mint animate-spin-slow" />
            <div className="absolute inset-2 rounded-full border-2 border-transparent border-b-mint animate-spin-slow-reverse" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-16 h-16 rounded-full bg-mint-light flex items-center justify-center">
                <span className="text-mint-dark text-2xl font-bold">D</span>
              </div>
            </div>
          </div>

          <p className="text-gray-900 text-lg font-medium mb-2">
            Waiting for DemoX to join the call
          </p>
          <p className="text-gray-500 text-sm">
            Preparing your demo{targetUrl ? ` of ${new URL(targetUrl.startsWith('http') ? targetUrl : 'https://' + targetUrl).hostname}` : ''}...
          </p>

          {/* Animated dots */}
          <div className="flex gap-1.5 mt-6">
            <div className="w-2 h-2 rounded-full bg-mint animate-bounce-dot" style={{ animationDelay: '0ms' }} />
            <div className="w-2 h-2 rounded-full bg-mint animate-bounce-dot" style={{ animationDelay: '150ms' }} />
            <div className="w-2 h-2 rounded-full bg-mint animate-bounce-dot" style={{ animationDelay: '300ms' }} />
          </div>
        </div>

        <style>{`
          @keyframes fade-in {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
          }
          .animate-fade-in {
            animation: fade-in 0.6s ease-out;
          }
          @keyframes spin-slow {
            to { transform: rotate(360deg); }
          }
          .animate-spin-slow {
            animation: spin-slow 3s linear infinite;
          }
          @keyframes spin-slow-reverse {
            to { transform: rotate(-360deg); }
          }
          .animate-spin-slow-reverse {
            animation: spin-slow-reverse 4s linear infinite;
          }
          @keyframes bounce-dot {
            0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
            40% { transform: translateY(-8px); opacity: 1; }
          }
          .animate-bounce-dot {
            animation: bounce-dot 1.2s ease-in-out infinite;
          }
        `}</style>
      </div>
    )
  }

  return (
    <div className="h-screen bg-gray-50 flex animate-call-enter">
      {/* Left: screen share + controls */}
      <div className="flex-1 flex flex-col relative">
        <ScreenShare screenshot={latestScreenshot} cursorPos={cursorPos} />

        {/* Back button */}
        <button
          onClick={() => {
            interruptCurrentResponse()
            clearAudioQueue()
            if (streamRef.current) {
              streamRef.current.getTracks().forEach(t => t.stop())
              streamRef.current = null
            }
            navigate('/')
          }}
          className="absolute top-4 left-4 z-20 px-3 py-1.5 bg-white border border-gray-300 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-colors text-sm flex items-center gap-1.5 shadow-sm"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back
        </button>

        {/* Participants panel overlay */}
        <div className="absolute top-4 right-4 flex gap-2 z-20">
          {/* DemoX tile */}
          <div className="w-28 h-20 rounded bg-gray-200 border border-gray-300 flex flex-col items-center justify-center">
            <div className="w-9 h-9 rounded-full bg-mint flex items-center justify-center mb-1">
              <span className="text-white text-xs font-semibold">D</span>
            </div>
            <span className="text-gray-500 text-[10px]">DemoX</span>
          </div>
          {/* You tile */}
          <div className="w-28 h-20 rounded bg-gray-200 border border-gray-300 flex flex-col items-center justify-center overflow-hidden relative">
            {isCameraOn ? (
              <>
                <video
                  ref={videoRef}
                  autoPlay
                  muted
                  playsInline
                  className="w-full h-full object-cover absolute inset-0"
                  style={{ transform: 'scaleX(-1)' }}
                />
                <span className="absolute bottom-1 text-white text-[10px] z-10 bg-black/50 px-1.5 rounded">You</span>
              </>
            ) : (
              <>
                <div className="w-9 h-9 rounded-full bg-gray-400 flex items-center justify-center mb-1">
                  <span className="text-white text-xs font-semibold">Y</span>
                </div>
                <span className="text-gray-500 text-[10px]">You</span>
              </>
            )}
          </div>
        </div>

        <ControlBar
          isMicOn={isListening}
          onToggleMic={toggleListening}
          micSupported={micSupported}
          isTranscribing={isTranscribing}
          isAudioOn={isAudioOn}
          onToggleAudio={toggleAudio}
          isCameraOn={isCameraOn}
          onToggleCamera={toggleCamera}
          isChatOpen={isChatOpen}
          onToggleChat={() => setIsChatOpen(prev => !prev)}
        />
      </div>

      {/* Right: chat (toggleable) */}
      {isChatOpen && (
        <ChatPanel
          messages={messages}
          onSendMessage={handleSendMessage}
          onInterrupt={interruptCurrentResponse}
          isLoading={isLoading}
        />
      )}

      <style>{`
        @keyframes call-enter {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        .animate-call-enter {
          animation: call-enter 0.5s ease-out;
        }
      `}</style>
    </div>
  )
}
