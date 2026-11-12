import type { Scene } from './playback'
import type { Node } from './types'
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

export function presentScene(scene: Scene): Scene {
  return { ...scene, nodes: scene.nodes.map(node => ({ ...node,
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
