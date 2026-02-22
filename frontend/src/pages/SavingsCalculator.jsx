import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function SavingsCalculator() {
  const navigate = useNavigate()
  const [demosPerWeek, setDemosPerWeek] = useState('')
  const [hoursPerDemo, setHoursPerDemo] = useState('')
  const [billingRate, setBillingRate] = useState('')
  const [results, setResults] = useState(null)
  const [showResults, setShowResults] = useState(false)

  const handleCalculate = () => {
    const demos = parseFloat(demosPerWeek)
    const hours = parseFloat(hoursPerDemo)
    const rate = parseFloat(billingRate)
    if (!demos || !hours || !rate) return

    const totalDemosPerYear = demos * 52
    const totalHoursPerYear = totalDemosPerYear * hours
    const totalCostPerYear = totalHoursPerYear * rate
    const demogorguxCost = totalDemosPerYear * 5
    const moneySaved = totalCostPerYear - demogorguxCost

    setShowResults(false)
    setResults({
      hoursSaved: totalHoursPerYear,
      moneySaved,
    })
    requestAnimationFrame(() => {
      requestAnimationFrame(() => setShowResults(true))
    })
  }

  const inputClass =
    'w-full px-5 py-3.5 bg-gray-800/80 border border-gray-700 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-green-500 focus:ring-1 focus:ring-green-500 transition-colors text-base'

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-green-500/5 rounded-full blur-3xl" />

      <div className="relative z-10 w-full max-w-md mx-auto px-4">
        <button
          onClick={() => navigate('/')}
          className="text-gray-400 hover:text-white transition-colors mb-8 flex items-center gap-2"
        >
          &larr; Back
        </button>

        <h1 className="text-4xl font-bold text-white tracking-tight mb-2 text-center">
          Savings Calculator
        </h1>
        <p className="text-gray-400 mb-8 text-center">
          See how much time and money Demogorgux saves you
        </p>

        <div className="flex flex-col gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Demos per week</label>
            <input
              type="number"
              min="0"
              value={demosPerWeek}
              onChange={(e) => setDemosPerWeek(e.target.value)}
              placeholder="e.g. 5"
              className={inputClass}
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Hours per demo</label>
            <input
              type="number"
              min="0"
              step="0.5"
              value={hoursPerDemo}
              onChange={(e) => setHoursPerDemo(e.target.value)}
              placeholder="e.g. 1.5"
              className={inputClass}
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1.5">Billing rate ($/hr)</label>
            <input
              type="number"
              min="0"
              value={billingRate}
              onChange={(e) => setBillingRate(e.target.value)}
              placeholder="e.g. 50"
              className={inputClass}
            />
          </div>

          <button
            onClick={handleCalculate}
            disabled={!demosPerWeek || !hoursPerDemo || !billingRate}
            className="w-full px-8 py-4 bg-green-600 hover:bg-green-500 text-white text-lg font-semibold rounded-xl transition-all duration-200 hover:scale-105 hover:shadow-lg hover:shadow-green-500/20 disabled:opacity-40 disabled:hover:scale-100 disabled:hover:bg-green-600 disabled:cursor-not-allowed mt-2"
          >
            Calculate
          </button>
        </div>

        {results && (
          <div
            className="mt-8 p-6 bg-gray-800/60 border border-gray-700 rounded-xl transition-all duration-700 ease-out"
            style={{
              opacity: showResults ? 1 : 0,
              transform: showResults ? 'translateY(0)' : 'translateY(20px)',
            }}
          >
            <h2 className="text-lg font-semibold text-white mb-4 text-center">
              Your Annual Savings
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 bg-gray-900/50 rounded-lg">
                <p className="text-3xl font-bold text-green-400">
                  {results.hoursSaved.toLocaleString()}
                </p>
                <p className="text-sm text-gray-400 mt-1">Hours saved</p>
              </div>
              <div className="text-center p-4 bg-gray-900/50 rounded-lg">
                <p className="text-3xl font-bold text-green-400">
                  ${results.moneySaved.toLocaleString()}
                </p>
                <p className="text-sm text-gray-400 mt-1">Money saved</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
