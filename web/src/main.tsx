import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { createStaticPlaybackSource } from './data/staticPlaybackSource.ts'
import { createHttpPlaybackSource } from './data/httpPlaybackSource.ts'

// Composition root: the ONLY place a concrete DataSource is chosen. A Postgres
// source later swaps in here the same way; views do not change.
const source = import.meta.env.VITE_PLAYBACK_API_BASE_URL
  ? createHttpPlaybackSource(import.meta.env.VITE_PLAYBACK_API_BASE_URL)
  : createStaticPlaybackSource()
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App source={source} />
  </StrictMode>,
)
