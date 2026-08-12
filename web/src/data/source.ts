import type { Bundle } from './types'

// Async by contract so file, HTTP, and future database sources share callers.
export interface DataSource {
  readonly name: string
  getBundle(): Promise<Bundle>
}
