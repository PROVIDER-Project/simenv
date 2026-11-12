import type { Scene } from './playback'
import type { Edge, Node } from './types'
import { GAZETTEER } from './gazetteer'

/** Recorded names are preserved in data; known shipped names get English UI labels. */
const germanNames: Record<string, string> = {
  brazil_farms: 'Sojaanbau Brasilien',
  argentina_farms: 'Sojaanbau Argentinien',
  us_farms: 'Sojaanbau USA',
  santos_port: 'Hafen Santos',
  paranagua_port: 'Hafen Paranaguá',
  rotterdam_port: 'Hafen Rotterdam',
  hamburg_port: 'Hafen Hamburg',
  eu_oil_mills: 'EU Ölmühlen',
  feed_mills: 'Futtermittelhersteller',
  poultry_farms: 'Geflügelbetriebe',
  pig_farms: 'Schweinebetriebe',
  dairy_farms: 'Milchwirtschaft',
  food_retail: 'Lebensmitteleinzelhandel',
  consumers: 'Verbraucher',
  alternative_protein_sources: 'Alternative Proteinquellen (Raps, Sonnenblume, Erbsen)',
  soy_oil_market: 'Sojaöl-Markt (Nebenprodukt Ölmühlen)',
  us_gulf_ports: 'US-Golfhäfen (New Orleans, Houston)',
  strategic_feed_reserves: 'Industrielle Futtermittel-Lagerbestände',
  gas_supply: 'Erdgasversorgung',
  fertilizer_supply: 'Düngemittelversorgung',
}
const additionalEnglishNames: Record<string, string> = {
  food_retail: 'Food retailers', consumers: 'Consumers',
  alternative_protein_sources: 'Alternative protein sources (rapeseed, sunflower, peas)',
  soy_oil_market: 'Soy oil market (oil-mill by-product)',
  us_gulf_ports: 'US Gulf ports (New Orleans, Houston)',
  strategic_feed_reserves: 'Strategic feed reserves', gas_supply: 'Natural gas supply',
  fertilizer_supply: 'Fertilizer supply',
}

function englishName(id: string): string {
  return GAZETTEER[id]?.label ?? additionalEnglishNames[id] ?? id
}

function displayLabel(label: string, entityIds: string[]): string {
  // Match both identity and exact shipped text. Custom English labels are not
  // overwritten merely because a run reuses a built-in entity ID.
  return label.split(' / ').map(part => {
    const id = entityIds.find(id => germanNames[id] === part)
    return id ? englishName(id) : part
  }).join(' / ')
}

/** Display originator-to-import routes without changing the recorded topology. */
function collapseExportWaypoints(scene: Scene): Scene {
  const nodes = new Map(scene.nodes.map(node => [node.id, node]))
  const transportRoles = new Set(['land_transport', 'sea_transport', 'port'])
  const candidates = scene.nodes.flatMap(node => {
    if (node.hasRecordedData !== false || !transportRoles.has(node.role)) return []
    const incoming = scene.edges.filter(edge => edge.target === node.id)
    const outgoing = scene.edges.filter(edge => edge.source === node.id)
    const supported = incoming.length && outgoing.length && incoming.every(edge => {
      const originator = nodes.get(edge.source)
      return edge.isSeaCrossing === false && originator?.hasRecordedData === true && originator.role === 'wholesaler'
    }) && outgoing.every(edge => edge.isSeaCrossing === true && nodes.has(edge.target) && edge.target !== node.id &&
      incoming.every(origin => origin.source !== edge.target))
    return supported ? [{ id: node.id, incoming, outgoing }] : []
  })
  if (!candidates.length) return scene

  const removed = new Set(candidates.map(node => node.id))
  const routeKey = (edge: Edge) => JSON.stringify([edge.source, edge.target, edge.isSeaCrossing])
  const routes = new Map<string, Edge>()
  // Original direct routes keep their IDs ahead of any replacement routes.
  for (const edge of scene.edges) {
    if (!removed.has(edge.source) && !removed.has(edge.target) && !routes.has(routeKey(edge))) routes.set(routeKey(edge), edge)
  }
  const replacements = new Map<string, Omit<Edge, 'id'>>()
  for (const node of candidates) {
    for (const origin of node.incoming) {
      for (const destination of node.outgoing) {
        const edge = { source: origin.source, target: destination.target, isSeaCrossing: true }
        replacements.set(JSON.stringify([edge.source, edge.target, true]), edge)
      }
    }
  }
  const usedIds = new Set(scene.edges.map(edge => edge.id))
  for (const key of [...replacements.keys()].sort()) {
    if (routes.has(key)) continue
    const base = `display:${key}`
    let id = base, suffix = 1
    while (usedIds.has(id)) id = `${base}:${suffix++}`
    usedIds.add(id)
    routes.set(key, { ...replacements.get(key)!, id })
  }
  return { ...scene, nodes: scene.nodes.filter(node => !removed.has(node.id)), edges: [...routes.values()] }
}

export function presentScene(scene: Scene): Scene {
  const display = collapseExportWaypoints(scene)
  return { ...display, nodes: display.nodes.map(node => ({ ...node,
    label: displayLabel(node.label, node.entityIds),
    placements: node.placements.map(placement => ({ ...placement,
      label: displayLabel(placement.label, [placement.entityId]),
    })),
  })) }
}

/** Member names for pooled components, distinct from their technical IDs. */
export function entityDisplayName(node: Node, id: string): string {
  return node.placements.find(placement => placement.entityId === id)?.label ?? englishName(id)
}
