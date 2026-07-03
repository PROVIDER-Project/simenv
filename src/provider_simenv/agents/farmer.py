"""
  role bra/arg/usa  Regional soja producers. All run one region-agnostic step:
                    output = base_yield * effective("capacity")
                    price = effective fixed_costs / delivered quantity * (1 + margin)
                    Producers differ only in their cost/margin parameters and which PDL shocks their archetype binds
                    (BRA binds fertilizer. Each binds its own entity's supply/capacity shock)
                    No producer is hardwired shock-immune or as a fixed surplus supplier.
                    (supply surges come from the PDL)

  role="eu"  European livestock farmer. End consumer of the chain.
             Receives feed from feed traders; produces livestock output.

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. Model applies the archetype params from topology.py: role, bindings,
     fixed_costs, margin, size_sigma, base_yield.
  3. agent.post_setup() → derives size factor, initial quantity and price.
"""
import numpy as np

from .base import SupplyChainAgent

ROLE_PRODUCER = "producer"
ROLE_EU = "eu"

class Farmer(SupplyChainAgent):
    """
    Agricultural actor — SA soja producer or EU livestock farmer.

    Shared state:
      role                  "sa" or "eu".
      fixed_costs           Operating cost per step (EUR/step).
      days_without_input   Consecutive days with zero input received.
      bankruptcy_threshold_days  Days without input before exiting the market.

    SA-specific state:
      base_yield    Max soja output under no disruption.
      margin        Profit ratio applied on per-unit cost.

    EU-specific state:
      feed_received     Feed obtained this step.
      livestock_output  Animal product output this step.
    """

    def setup(self):
        """Zero-initialise all fields. Role not known yet."""
        super().setup()
        self.role: str = ""
        self.fixed_costs: float = 0.0
        self.days_without_input: int = 0
        self.bankruptcy_threshold_days: int = 21    # 3 weeks without feed = exit market

        # SA-specific
        self.base_yield: float = 0.0
        self.margin: float = 0.0

        # EU-specific
        self.feed_received: float = 0.0
        self.livestock_output: float = 0.0

        # size heterogeneity (size_sigma is set from archetype params by the model)
        self.size_sigma: float = 0.0
        self.size_factor: float = 1.0

    def _sample_size_factor(self, sigma: float) -> float:
        """
        sample a log-normal size factor for this agent.

        sigma = 0.0 -> always 1.0 (all agents identical)
        sigma > 0.0 -> log-normal draw centered at 1.0

        seed is agent specific so each agent gets a unique
        but reproducible draw independent of iteration order.
        """
        if sigma == 0.0:
            return 1.0
        rng = np.random.default_rng(self.scenario.farm_size_seed + self.id)
        return float(rng.lognormal(mean=0.0, sigma=sigma))

    def post_setup(self):
        """
        Derived initialisation from the archetype params the model applied
        (fixed_costs, margin, size_sigma, base_yield).

        Producers (base_yield > 0) start priced cost-based at full yield.
        Consumers (base_yield == 0, e.g. EU livestock) fall through with
        quantity_available = 0 and unit_price 0.0 — they are buyers.
        """
        self.size_factor = self._sample_size_factor(self.size_sigma)
        self.base_yield *= self.size_factor
        self.fixed_costs *= self.size_factor

        self.quantity_available = self.base_yield
        if self.quantity_available > 0:
            self.unit_price = (
                self.fixed_costs / self.quantity_available
            ) * (1.0 + self.margin)

    def step(self, drought_severity: float = 0.0):
        if not self.active:
            return
        elif self.role == ROLE_EU:
            self._step_eu()
        else:
            self._step_producer()       # bra / arg / usa all run one regional-agnostic

    # -------------------------------------------------
    # Producer: produce soja, price from fixed costs.
    # Region-agnostic every producer runs this same path
    # regions differ only in params and bindings
    # -------------------------------------------------
    def _step_producer(self):
        """
        Produce soja this step.

        Output = base_yield * effective("capacity")
        effective("capacity") is this producer's own supply-shock multiplier (1.0 when unbound)
        so a drought or a supply event scales output directly. Lower output raises the per unit price.
        effective("fertilizer") (1.0 when unbound) raises effective fixed costs this step for producers that bind it (BRA)
        """
        capacity = self.effective("capacity")
        self.quantity_available = self.base_yield * capacity

        if self.quantity_available > 0:
            effective_costs = self.fixed_costs * self.effective("fertilizer")
            self.unit_price = (effective_costs / self.quantity_available) * (1.0 + self.margin)
        else:
            self.unit_price = 0.0


    # --------------------------------------------------
    # EU farmer: receive feed, compute livestock output
    # --------------------------------------------------

    def _step_eu(self):
        """
        Collect feed from all feed traders (equal share per EU farmer),
        then compute livestock output proportional to feed received.
        """
        active_eu = self.model.eu_farmers.filter(lambda f: f.active)
        n_eu = len(active_eu)
        active_traders = self.model.upstream("eu_farmers")
        total_feed = sum(t.quantity_available for t in active_traders)
        self.feed_received = total_feed / n_eu if n_eu > 0 else 0.0

        # 100 units of feed → 100 units of livestock output (baseline).
        self.livestock_output = self.feed_received

        # Bankruptcy counter
        if self.feed_received == 0.0:
            self.days_without_input += 1
        else:
            self.days_without_input = 0

        if self.days_without_input >= self.bankruptcy_threshold_days:
            self.active = False
