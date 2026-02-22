import { useState, useRef, useEffect } from 'react'

export default function ChatPanel({ messages, onSendMessage, onInterrupt, isLoading }) {
  const [input, setInput] = useState('')
  const chatEndRef = useRef(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = () => {
    if (!input.trim()) return
    onSendMessage(input.trim())
    setInput('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInputChange = (e) => {
    const nextValue = e.target.value
    if (isLoading && onInterrupt && !input.trim() && nextValue.trim()) {
      onInterrupt()
    }
    setInput(nextValue)
  }

  return (
    <div className="w-96 bg-gray-900 border-l border-gray-800 flex flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <p className="text-gray-600 text-sm text-center mt-8">
            Send a message or use your mic to talk to the agent.
          </p>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`max-w-[85%] px-4 py-2.5 rounded-xl text-sm leading-relaxed break-words ${
              msg.type === 'user'
                ? 'bg-blue-600 text-white self-end ml-auto rounded-br-sm'
                : msg.interrupted
                  ? 'bg-gray-800 text-gray-400 rounded-bl-sm italic opacity-60'
                  : 'bg-gray-800 text-gray-200 rounded-bl-sm'
            }`}
          >
            {msg.content}
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-800">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Tell me what to show you..."
            className="flex-1 px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 outline-none focus:border-blue-500 transition-colors"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {isLoading ? 'Interrupt + Send' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
