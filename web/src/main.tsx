import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { staticJsonSource } from './data/staticJsonSource.ts'

// Composition root: the only place a concrete DataSource is chosen.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App source={staticJsonSource} />
  </StrictMode>,
)
