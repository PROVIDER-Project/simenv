"""
Simulation scenario parameters.

A Scenario in Melodie holds all input parameters for one simulation run.
"""

from Melodie import Scenario

class SupplyChainScenario(Scenario):
    """
    Defines one concrete run of the supply chain simulation.

    All numeric fields are read by Melodie from the scenarios table.
    """

    # --- KG shock coefficients ---
    farm_capacity_bra: float = 1.0  # BRA soja farm output multiplier (0.7 = 30% drought loss)

    port_capacity_sa: float = 1.0   # SA port throughput multiplier

    fertilizer_price_factor: float = 1.0 # multiplier on SA farmer fixed costs (1.3 = + 30%)
    energy_price_factor: float = 1.0    # multiplier on all transport fixed costs (1.5 = + 50%)

    oil_mill_capacity: float = 1.0  # EU processor output multiplier (0.95 = slight soja shortage)
    feed_mill_capacity: float = 1.0     # feed manufacturer output multiplier

    shock_onset_setup: int = 0
    shock_ramp_steps: int = 0

    # --- Agent population size ---
    n_sa_farmers: int = 10          # South American Farmers
    n_wholesalers: int = 3          # buys from farmers, aggregate them, sell internationally
    n_transport_sa: int = 2         # land transport, South America
    n_transport_sea: int = 2        # maritime transport
    n_transport_eu: int = 2         # land transport, EU
    n_processors: int = 3           # Crushers / Verschrotung
    n_feed_manufacturers: int = 3
    n_feed_traders: int = 3
    n_eu_farmers: int = 10          # EU livestock farmers

    # --- Fixed costs (€/step) ---
    # Total operating cost an agent pays each step regardless of volume.
    # the resulting price chain stays in a plausible EUR/ton range.
    fixed_costs_sa_farmer: float = 36000.0          # farm labor, land, machinery
    fixed_costs_eu_farmer: float = 5000.0           # livestock farm operating cost
    fixed_costs_wholesaler: float = 15000.0         # aggregation, storage, logistics
    fixed_costs_feed_trader: float = 8000.0         # distribution, warehousing
    fixed_costs_transport_sa: float = 9000.0        # SA land freight
    fixed_costs_transport_sea: float = 45000.0      # atlantic shipping
    fixed_costs_transport_eu: float = 7000.0        # EU lang freight
    fixed_costs_processor: float = 20000.0          # Crushing plant operation
    fixed_costs_feed_manufacturer: float = 12000.0  # feed compounding plant

    # --- Margins ---
    # applied on top of total per unit cost at each chain node.
    margin_sa_farmer: float = 0.10
    margin_wholesaler: float = 0.10
    margin_feed_trader: float = 0.08
    margin_transport: float = 0.10          # shared across all transport roles
    margin_processor: float = 0.12
    margin_feed_manufacturer: float = 0.10

    # Simulation length (Number of steps)
    period_num: int = 52            # week in a year


