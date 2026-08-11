import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { staticJsonSource } from './data/staticJsonSource.ts'

// Composition root: the ONLY place a concrete DataSource is chosen. This swap
// from `fixtureSource` to `staticJsonSource` (the exported run) touches no view
// file — the seam's proof. A Postgres source later swaps in here the same way.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App source={staticJsonSource} />
  </StrictMode>,
)
