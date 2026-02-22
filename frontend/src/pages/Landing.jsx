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
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center relative overflow-hidden">
      <div className="relative z-10 text-center animate-fade-in">
        <h1 className="text-6xl font-bold text-gray-900 tracking-tight mb-3">
          DemoX
        </h1>
        <p className="text-xl text-gray-500 mb-10">
          Automating <span className="font-bold">demos</span> so you can focus on what actually matters
        </p>

        <div className="flex flex-col items-center gap-4 max-w-lg mx-auto">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter a website URL to demo (e.g. https://example.com)"
            className="w-full px-5 py-3.5 bg-gray-100 border border-black rounded text-gray-900 placeholder-gray-400 focus:outline-none focus:border-mint focus:ring-1 focus:ring-mint transition-colors text-base"
          />
          <div className="flex items-center gap-4 w-full">
            <button
              onClick={handleLaunch}
              disabled={!url.trim()}
              className="flex-1 px-8 py-3 bg-gray-200 hover:bg-gray-300 text-gray-700 text-base font-semibold rounded border border-gray-300 transition-all duration-200 hover:shadow-md disabled:opacity-40 disabled:hover:bg-gray-200 disabled:cursor-not-allowed"
            >
              Launch Demo
            </button>
            <button
              onClick={() => navigate('/demo?url=' + encodeURIComponent('https://monkeytype.com'))}
              className="flex-1 px-8 py-3 bg-gray-800 hover:bg-gray-700 text-white text-base font-semibold rounded transition-all duration-200 hover:shadow-md"
            >
              Demo Monkeytype
            </button>
          </div>

          <div className="w-full h-px bg-gray-200 mt-6" />

          <button
            onClick={() => navigate('/savings')}
            className="w-full px-8 py-3 bg-mint hover:bg-mint-hover text-white text-base font-semibold rounded transition-all duration-200 hover:shadow-md mt-4"
          >
            Calculate Savings
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
