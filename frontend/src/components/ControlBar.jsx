export default function ControlBar({
  isMicOn,
  onToggleMic,
  micSupported,
  isTranscribing = false,
  isAudioOn,
  onToggleAudio,
  isCameraOn,
  onToggleCamera,
  isChatOpen,
  onToggleChat,
  chatOnly = false,
}) {
  return (
    <div className="h-16 bg-white border-t border-gray-200 flex items-center px-6 gap-3">
      {!chatOnly && (
        <button
          onClick={onToggleMic}
          disabled={!micSupported || isTranscribing}
          className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors relative ${
            isMicOn
              ? 'bg-mint text-white'
              : 'bg-gray-200 text-gray-500 hover:bg-gray-300'
          } ${isTranscribing ? 'animate-pulse' : ''} ${!micSupported ? 'opacity-40 cursor-not-allowed' : ''}`}
          title={isTranscribing ? 'Transcribing...' : !micSupported ? 'Microphone not available' : isMicOn ? 'Mute mic' : 'Unmute mic'}
        >
          {isMicOn ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3l18 18" />
            </svg>
          )}
        </button>
      )}

      {/* Speaker button */}
      <button
        onClick={onToggleAudio}
        className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${
          isAudioOn
            ? 'bg-mint text-white'
            : 'bg-gray-200 text-gray-500 hover:bg-gray-300'
        }`}
        title={isAudioOn ? 'Mute agent audio' : 'Unmute agent audio'}
      >
        {isAudioOn ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M15.536 8.464a5 5 0 010 7.072M17.95 6.05a8 8 0 010 11.9M6.5 8H4a1 1 0 00-1 1v6a1 1 0 001 1h2.5l4.5 4V4l-4.5 4z" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
          </svg>
        )}
      </button>

      {/* Camera button */}
      <button
        onClick={onToggleCamera}
        className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${
          isCameraOn
            ? 'bg-mint text-white'
            : 'bg-gray-200 text-gray-500 hover:bg-gray-300'
        }`}
        title={isCameraOn ? 'Turn off camera' : 'Turn on camera'}
      >
        {isCameraOn ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3l18 18" />
          </svg>
        )}
      </button>

      <div className="flex-1" />

      {/* Chat toggle button */}
      <button
        onClick={onToggleChat}
        className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${
          isChatOpen
            ? 'bg-mint text-white'
            : 'bg-gray-200 text-gray-500 hover:bg-gray-300'
        }`}
        title={isChatOpen ? 'Close chat' : 'Open chat'}
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      </button>
    </div>
  )
}
