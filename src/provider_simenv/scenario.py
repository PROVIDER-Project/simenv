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

    port_capacity_santos: float = 1.0    # Santos port throughput multiplier
    port_capacity_paranagua: float = 1.0 # Paranagua port throughput multiplier
    port_capacity_rotterdam: float = 1.0    # Rotterdam port throughput multiplier
    port_capacity_hamburg: float = 1.0      # Hamburg port throughput multiplier
    santos_share: float = 0.7   # 0.7 = 70% of BRA exports via Santos

    fertilizer_price_factor: float = 1.0 # multiplier on SA farmer fixed costs (1.3 = + 30%)
    energy_price_factor: float = 1.0    # multiplier on all transport fixed costs (1.5 = + 50%)

    oil_mill_capacity: float = 1.0  # EU processor output multiplier (0.95 = slight soja shortage)
    feed_mill_capacity: float = 1.0     # feed manufacturer output multiplier

    shock_onset_setup: int = 0
    shock_ramp_steps: int = 0

    # --- Agent population size ---
    n_bra_farmers: int = 10         # South American Farmers
    n_wholesalers: int = 3          # buys from farmers, aggregate them, sell internationally
    n_transport_sa_santos: int = 1  # Agents handling the Santos lane
    n_transport_sa_paranagua: int = 1   # Agents handling the Paranagua lane
    n_sea_lane_santos: int = 1        # Sea agents: Santos -> Rotterdam
    n_sea_lane_paranagua: int = 1     # Sea agents: Paranagua -> Hamburg
    n_sea_lane_arg: int = 1           # Sea agents: ARG direct -> Rotterdam
    n_sea_lane_usa: int = 1           # Sea agents: USA Gulf -> Rotterdam
    n_transport_eu_rtm: int = 1         # Rotterdam EU entry port agents
    n_transport_eu_ham: int = 1         # Hamburg EU entry port agents
    n_processors: int = 3           # Crushers / Verschrotung
    n_feed_manufacturers: int = 3
    n_feed_traders: int = 3
    n_eu_farmers: int = 10          # EU livestock farmers

    # --- Storage capacities (t/step)
    # Maximum inventory a wholesaler can hold in a single simulation step
    # set to realistic value (e.g. 20_000) to observe capacity-binding behavior under brazil_drought scenario.
    wholesaler_storage_capacity: float = 20_000.0



    # --- Fixed costs (€/step) ---
    # Total operating cost an agent pays each step regardless of volume.
    # the resulting price chain stays in a plausible EUR/ton range.
    fixed_costs_bra_farmer: float = 36000.0          # farm labor, land, machinery
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
    margin_bra_farmer: float = 0.10
    margin_wholesaler: float = 0.10
    margin_feed_trader: float = 0.08
    margin_transport: float = 0.10          # shared across all transport roles
    margin_processor: float = 0.12
    margin_feed_manufacturer: float = 0.10

    # Simulation length (Number of steps)
    period_num: int = 52            # week in a year

    # Farm size heterogeneity
    # log-normal size distribution for BRA, USA and EU farmers.
    # sigma = 0.0 -> all farms identical
    # sigma = 0.4 -> realistic spread (most farms near mean, few very large/small)
    farm_size_sigma_bra: float = 0.0
    farm_size_sigma_usa: float = 0.0
    farm_size_sigma_arg: float = 0.0
    farm_size_sigma_eu: float = 0.0
    farm_size_seed: int = 42

    # --- USA farmer parameters ---
    # USA farmers are structurally identical to BRA farmers:
    #   - higher fixed_costs -> higher baseline price (EU prefers BRA under normal conditions)
    #   - unaffected by BRA shock -> stable supply when BRA supply is disrupted
    #   - base_yield acts as capacity ceiling
    n_usa_farmers: int = 8
    fixed_costs_usa_farmer: float = 48000.0
    margin_usa_farmer: float = 0.10
    usa_surplus_factor: float = 1.5


    # --- Argentina farmer parameters ---
    # Argentina is a permanent always-on baseline supplier:
    #   - fixed_costs between BRA and USA
    #   - unaffected by BRA shock
    #   - No surplus_factor - ARG is a baseline supply, not emergency reserve
    n_arg_farmers: int = 5
    fixed_costs_arg_farmer: float = 42000.0
    margin_arg_farmer: float = 0.10
    farm_capacity_arg: float = 1.0  # ARG output multiplier (1.0 = unshocked)


