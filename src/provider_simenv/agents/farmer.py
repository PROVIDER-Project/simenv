"""
  role="sa"  South American soja producer. First actor in the chain.
             Produces soja; price = (fixed_costs / qty) * (1 + margin).

  role="eu"  European livestock farmer. End consumer of the chain.
             Receives feed from feed traders; produces livestock output.

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. agent.role = …    → Model assigns the role.
  3. agent.post_setup() → Reads fixed_costs/margin from scenario.
"""
import numpy as np

from .base import SupplyChainAgent

ROLE_SA = "sa"
ROLE_EU = "eu"


class Farmer(SupplyChainAgent):
    """
    Agricultural actor — SA soja producer or EU livestock farmer.

    Shared state:
      role                  "sa" or "eu".
      fixed_costs           Operating cost per step (EUR/step).
      steps_without_input   Consecutive steps with zero input received.
      bankruptcy_threshold  Exit market when counter exceeds this.

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
        self.steps_without_input: int = 0
        self.bankruptcy_threshold: int = 3

        # SA-specific
        self.base_yield: float = 0.0
        self.margin: float = 0.0

        # EU-specific
        self.feed_received: float = 0.0
        self.livestock_output: float = 0.0

        # size heterogeneity
        self. size_factor: float = 1.0

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
        """Role-specific initialisation after role is assigned by model."""
        if self.role == ROLE_SA:
            self.fixed_costs = self.scenario.fixed_costs_sa_farmer
            self.margin = self.scenario.margin_sa_farmer
            self.base_yield = 100.0     # Placeholder

            # scale by size factor
            # baseline unit_price is size-independent (for now)
            # Heterogeneity emerges under shock: small farms lose output faster and exit the market
            self.size_factor = self._sample_size_factor(self.scenario.farm_size_sigma_sa)
            self.base_yield *= self.size_factor
            self.fixed_costs *= self.size_factor

            # Initial price: cost-based at full yield, no disruption
            self.quantity_available = self.base_yield
            if self.quantity_available > 0:
                self.unit_price = (
                    self.fixed_costs / self.quantity_available
                ) * (1.0 + self.margin)

        elif self.role == ROLE_EU:
            self.fixed_costs = self.scenario.fixed_costs_eu_farmer
            self.size_factor = self._sample_size_factor(self.scenario.farm_size_sigma_eu)
            self.fixed_costs *= self.size_factor
            self.feed_received = 0.0
            self.livestock_output = 0.0
            self.unit_price = 0.0       # EU farmers are buyers
            self.quantity_available = 0.0

    def step(self, drought_severity: float = 0.0):
        if not self.active:
            return
        if self.role == ROLE_SA:
            self._step_sa()
        elif self.role == ROLE_EU:
            self._step_eu()

    # -------------------------------------------------
    # SA farmer: produce soja, price from fixed costs
    # -------------------------------------------------

    def _step_sa(self):
        """
        Produce soja this step. Drought reduces output; lower output
        raises per-unit cost, which raises unit_price automatically.
        """
        shock_scale = self.model.environment.shock_scale
        farm_capacity = 1.0 + shock_scale * (self.scenario.farm_capacity_bra - 1.0)
        self.quantity_available = self.base_yield * farm_capacity
        if self.quantity_available > 0:
            # fertilizer price factor raises effective fixed costs this step
            fertilizer_factor = 1.0 + shock_scale * (self.scenario.fertilizer_price_factor - 1.0)
            effective_costs = self.fixed_costs * fertilizer_factor
            self.unit_price = (effective_costs / self.quantity_available) * (1.0 + self.margin)
        else:
            # total crop failure - price undefined, agent cannot trade
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
        active_traders = self.model.feed_traders.filter(lambda t: t.active)
        total_feed = sum(t.quantity_available for t in active_traders)
        self.feed_received = total_feed / n_eu if n_eu > 0 else 0.0

        # 100 units of feed → 100 units of livestock output (baseline).
        self.livestock_output = self.feed_received

        # Bankruptcy counter
        if self.feed_received == 0.0:
            self.steps_without_input += 1
        else:
            self.steps_without_input = 0

        if self.steps_without_input >= self.bankruptcy_threshold:
            self.active = False
