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

    # --- Supply chain routing ---
    santos_share: float = 0.7   # 70% of BRA exports via Santos

    # --- Agent population size ---
    n_brazil_farms: int = 10         # South American Farmers
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
    # 20 000 t / week -> 2857 t / day
    wholesaler_storage_capacity: float = 2_857.0



    # --- Fixed costs (€/step) ---
    # Total operating cost an agent pays each step regardless of volume.
    # the resulting price chain stays in a plausible EUR/ton range.
    fixed_costs_brazil_farms: float = 36000.0          # farm labor, land, machinery
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
    margin_brazil_farms: float = 0.10
    margin_wholesaler: float = 0.10
    margin_feed_trader: float = 0.08
    margin_transport: float = 0.10          # shared across all transport roles
    margin_processor: float = 0.12
    margin_feed_manufacturer: float = 0.10

    # Simulation length (Number of steps)
    period_num: int = 365            # days in a year

    # Farm size heterogeneity
    # log-normal size distribution for BRA, USA and EU farmers.
    # sigma = 0.0 -> all farms identical
    # sigma = 0.4 -> realistic spread (most farms near mean, few very large/small)
    size_sigma_brazil_farms: float = 0.0
    size_sigma_us_farms: float = 0.0
    size_sigma_argentina_farms: float = 0.0
    farm_size_sigma_eu: float = 0.0
    farm_size_seed: int = 42

    # --- USA farmer parameters ---
    # USA farmers are structurally identical to BRA farmers:
    #   - higher fixed_costs -> higher baseline price (EU prefers BRA under normal conditions)
    #   - unaffected by BRA shock -> stable supply when BRA supply is disrupted
    #   - base_yield acts as capacity ceiling
    n_us_farms: int = 8
    fixed_costs_us_farms: float = 48000.0
    margin_us_farms: float = 0.10


    # --- Argentina farmer parameters ---
    # Argentina is a permanent always-on baseline supplier:
    #   - fixed_costs between BRA and USA
    #   - unaffected by BRA shock
    #   - No surplus_factor - ARG is a baseline supply, not emergency reserve
    n_argentina_farms: int = 5
    fixed_costs_argentina_farms: float = 42000.0
    margin_argentina_farms: float = 0.10

    # generic producer fallback: synthetic sentinels, not a real country's costs
    fixed_costs_producer: float = 1.0
    margin_producer: float = 0.10
    size_sigma_producer: float = 0.0
    n_producer: int = 1


