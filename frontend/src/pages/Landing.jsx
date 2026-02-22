import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Landing() {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')

  const handleLaunch = () => {
    const targetUrl = url.trim()
    if (!targetUrl) return
    navigate(`/demo?url=${encodeURIComponent(targetUrl)}`)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && url.trim()) {
      handleLaunch()
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-500/5 rounded-full blur-3xl" />

      <div className="relative z-10 text-center animate-fade-in">
        <h1 className="text-6xl font-bold text-white tracking-tight mb-3">
          Demogorgux
        </h1>
        <p className="text-xl text-gray-400 mb-10">
          Automating demos so you can focus on what actually matters
        </p>

        <div className="flex flex-col items-center gap-4 max-w-lg mx-auto">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter a website URL to demo (e.g. https://example.com)"
            className="w-full px-5 py-3.5 bg-gray-800/80 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors text-base"
          />
          <button
            onClick={handleLaunch}
            disabled={!url.trim()}
            className="px-8 py-4 bg-blue-600 hover:bg-blue-500 text-white text-lg font-semibold rounded-xl transition-all duration-200 hover:scale-105 hover:shadow-lg hover:shadow-blue-500/20 disabled:opacity-40 disabled:hover:scale-100 disabled:hover:bg-blue-600 disabled:cursor-not-allowed"
          >
            Launch Demo
          </button>

          <div className="flex items-center gap-3 w-full mt-2">
            <div className="flex-1 h-px bg-gray-700" />
            <span className="text-gray-500 text-sm">or</span>
            <div className="flex-1 h-px bg-gray-700" />
          </div>

          <button
            onClick={() => navigate('/demo?url=' + encodeURIComponent('https://monkeytype.com'))}
            className="px-6 py-3 bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-sm font-medium rounded-xl border border-gray-700 transition-all duration-200 hover:scale-105"
          >
            Demo Monkeytype
          </button>
        </div>
      </div>

      <style>{`
        @keyframes fade-in {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in {
          animation: fade-in 0.8s ease-out;
        }
      `}</style>
    </div>
  )
}
