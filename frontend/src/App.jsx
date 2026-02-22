import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import Demo from './pages/Demo'
import SavingsCalculator from './pages/SavingsCalculator'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/demo" element={<Demo />} />
        <Route path="/savings" element={<SavingsCalculator />} />
      </Routes>
    </BrowserRouter>
  )
}
