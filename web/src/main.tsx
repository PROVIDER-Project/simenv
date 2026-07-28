import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { fixtureSource } from './data/fixtureSource.ts'

// Composition root: the ONLY place a concrete DataSource is chosen. Swapping
// `fixtureSource` for `staticJsonSource` (Batch 5) or a Postgres source later
// happens here and touches no view file.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App source={fixtureSource} />
  </StrictMode>,
)
