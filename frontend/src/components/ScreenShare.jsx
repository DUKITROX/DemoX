import { useRef, useEffect, useState } from 'react'

export default function ScreenShare({ screenshot, cursorPos }) {
  const containerRef = useRef(null)
  const imgRef = useRef(null)
  const [imgScale, setImgScale] = useState({ scaleX: 1, scaleY: 1, offsetX: 0, offsetY: 0 })
  const prevScreenshotRef = useRef(null)
  const [fadingOut, setFadingOut] = useState(null) // holds the old screenshot src during fade

  // Cursor trail: track recent positions for a subtle motion trail
  const trailRef = useRef([])
  const [cursorTrail, setCursorTrail] = useState([])

  useEffect(() => {
    if (!cursorPos) return
    const now = Date.now()
    trailRef.current = [...trailRef.current, { ...cursorPos, time: now }]
      .filter(p => now - p.time < 300) // Keep last 300ms of positions
      .slice(-5) // Max 5 trail dots
    setCursorTrail([...trailRef.current])
  }, [cursorPos])

  // Crossfade: when screenshot changes, animate old one fading out
  useEffect(() => {
    if (screenshot && prevScreenshotRef.current && screenshot !== prevScreenshotRef.current) {
      setFadingOut(prevScreenshotRef.current)
      const timer = setTimeout(() => setFadingOut(null), 500)
      prevScreenshotRef.current = screenshot
      return () => clearTimeout(timer)
    }
    prevScreenshotRef.current = screenshot
  }, [screenshot])

  // Compute scale mapping from 1280x800 browser coords to rendered image size
  useEffect(() => {
    const updateScale = () => {
      const img = imgRef.current
      if (!img) return
      const rect = img.getBoundingClientRect()
      const container = containerRef.current
      if (!container) return
      const containerRect = container.getBoundingClientRect()
      setImgScale({
        scaleX: rect.width / 1280,
        scaleY: rect.height / 800,
        offsetX: rect.left - containerRect.left,
        offsetY: rect.top - containerRect.top,
      })
    }

    updateScale()
    window.addEventListener('resize', updateScale)
    return () => window.removeEventListener('resize', updateScale)
  }, [screenshot])

  return (
    <div ref={containerRef} className="flex-1 flex items-center justify-center bg-gray-100 p-4 overflow-hidden relative">
      {screenshot ? (
        <>
          {/* Previous screenshot fading out during crossfade */}
          {fadingOut && (
            <img
              src={fadingOut}
              alt=""
              className="absolute max-w-full max-h-full rounded-lg border border-gray-200 shadow-lg pointer-events-none"
              style={{
                animation: 'screenshotFadeOut 0.5s ease-out forwards',
              }}
            />
          )}
          <img
            ref={imgRef}
            src={screenshot}
            alt="Agent screen"
            className="max-w-full max-h-full rounded-lg border border-gray-200 shadow-lg"
            decoding="async"
            style={{
              transition: 'opacity 0.3s ease-in',
              opacity: 1,
            }}
            onLoad={() => {
              const img = imgRef.current
              if (!img) return
              const container = containerRef.current
              if (!container) return
              const rect = img.getBoundingClientRect()
              const containerRect = container.getBoundingClientRect()
              setImgScale({
                scaleX: rect.width / 1280,
                scaleY: rect.height / 800,
                offsetX: rect.left - containerRect.left,
                offsetY: rect.top - containerRect.top,
              })
            }}
          />
          {/* Cursor trail dots */}
          {cursorTrail.map((pos, i) => (
            <div
              key={i}
              className="absolute rounded-full pointer-events-none"
              style={{
                left: imgScale.offsetX + pos.x * imgScale.scaleX,
                top: imgScale.offsetY + pos.y * imgScale.scaleY,
                width: 4,
                height: 4,
                backgroundColor: 'rgba(0, 0, 0, 0.1)',
                opacity: 0.15 + (i / cursorTrail.length) * 0.25,
                transition: 'opacity 0.2s ease-out',
                zIndex: 9,
              }}
            />
          ))}
          {/* Animated cursor overlay */}
          {cursorPos && (
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="absolute pointer-events-none"
              style={{
                left: imgScale.offsetX + cursorPos.x * imgScale.scaleX,
                top: imgScale.offsetY + cursorPos.y * imgScale.scaleY,
                transition: 'left 0.15s cubic-bezier(0.25, 0.1, 0.25, 1), top 0.15s cubic-bezier(0.25, 0.1, 0.25, 1)',
                zIndex: 10,
                filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.5))',
              }}
            >
              <path
                d="M5.5 3.21V20.8L9.6 16.7L12.5 22.8L15.3 21.4L12.4 15.3H18.6L5.5 3.21Z"
                fill="white"
                stroke="black"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </>
      ) : (
        <div className="text-gray-400 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-200 flex items-center justify-center">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <p className="text-sm">Waiting for agent screen share...</p>
        </div>
      )}

      {/* Keyframe animation for screenshot crossfade */}
      <style>{`
        @keyframes screenshotFadeOut {
          from { opacity: 1; }
          to { opacity: 0; }
        }
      `}</style>
    </div>
  )
}
