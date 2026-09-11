/**
 * The DataSource seam (Issue #23, locked decision).
 *
 * Every view depends on THIS interface and never on a concrete source. Today
 * `staticJsonSource` reads the exported bundle; a `PostgresSource` follows later
 * when palaestrAI connects. Because views only ever see `DataSource`, those
 * swaps touch zero view files — that swappability is the whole point of the seam.
 *
 * The interface is intentionally async (returns a Promise) so a network- or
 * DB-backed implementation fits without changing any caller.
 */

import type { Bundle } from './types'

export interface DataSource {
  /** A short identifier for the active source, useful for diagnostics/UI. */
  readonly name: string

  /** Load the full bundle for the current run. */
  getBundle(): Promise<Bundle>
}
