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
    'w-full px-5 py-3.5 bg-gray-100 border border-black rounded text-gray-900 placeholder-gray-400 focus:outline-none focus:border-mint focus:ring-1 focus:ring-mint transition-colors text-base'

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center relative overflow-hidden">
      <div className="relative z-10 w-full max-w-md mx-auto px-4">
        <button
          onClick={() => navigate('/')}
          className="text-gray-500 hover:text-gray-900 transition-colors mb-8 flex items-center gap-2"
        >
          &larr; Back
        </button>

        <h1 className="text-4xl font-bold text-gray-900 tracking-tight mb-2 text-center">
          Savings Calculator
        </h1>
        <p className="text-gray-500 mb-8 text-center">
          See how much time and money DemoX could save you
        </p>

        <div className="flex flex-col gap-4">
          <div>
            <label className="block text-sm text-gray-500 mb-1.5">Demos per week</label>
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
            <label className="block text-sm text-gray-500 mb-1.5">Hours per demo</label>
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
            <label className="block text-sm text-gray-500 mb-1.5">Billing rate ($/hr)</label>
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
            className="w-full px-8 py-4 bg-mint hover:bg-mint-hover text-white text-lg font-semibold rounded transition-all duration-200 hover:shadow-md disabled:opacity-40 disabled:hover:bg-mint disabled:cursor-not-allowed mt-2"
          >
            Calculate
          </button>
        </div>

        {results && (
          <div
            className="mt-8 p-6 bg-gray-100 border border-gray-300 rounded transition-all duration-700 ease-out"
            style={{
              opacity: showResults ? 1 : 0,
              transform: showResults ? 'translateY(0)' : 'translateY(20px)',
            }}
          >
            <h2 className="text-lg font-semibold text-gray-900 mb-4 text-center">
              Your Annual Savings
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 bg-gray-200 rounded">
                <p className="text-3xl font-bold text-mint">
                  {results.hoursSaved.toLocaleString()}
                </p>
                <p className="text-sm text-gray-500 mt-1">Hours saved</p>
              </div>
              <div className="text-center p-4 bg-gray-200 rounded">
                <p className="text-3xl font-bold text-mint">
                  ${results.moneySaved.toLocaleString()}
                </p>
                <p className="text-sm text-gray-500 mt-1">Money saved</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
