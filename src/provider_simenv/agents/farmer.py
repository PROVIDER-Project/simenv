"""
  role="bra" Brazilian soja producer. First actor in the chain.
             Produces soja; price = (fixed_costs / qty) * (1 + margin).

  role="arg" Argentine soja producer. Always-on baseline supplier.
             Same price formula as BRA, not affected by BRA shock.
             fixed_costs between BRA and USA -> price sits between them at baseline.
             farm_capacity_arg allows independent ARG-specific shocks

  role="usa" US soja producer. Alternative supplier to BRA.
             Same price formula as BRA but not affected by BRA/SA shock.
             Higher fixed_costs -> higher baseline price than BRA and ARG.
             base_yield acts as a hard capacity ceiling.

  role="eu"  European livestock farmer. End consumer of the chain.
             Receives feed from feed traders; produces livestock output.

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. agent.role = …    → Model assigns the role.
  3. agent.post_setup() → Reads fixed_costs/margin from scenario.
"""
import numpy as np

from .base import SupplyChainAgent

ROLE_BRA = "bra"
ROLE_ARG = "arg"
ROLE_USA = "usa"
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
        if self.role == ROLE_BRA:
            self.fixed_costs = self.scenario.fixed_costs_bra_farmer
            self.margin = self.scenario.margin_bra_farmer
            self.base_yield = 100.0     # Placeholder

            # scale by size factor
            # baseline unit_price is size-independent (for now)
            # Heterogeneity emerges under shock: small farms lose output faster and exit the market
            self.size_factor = self._sample_size_factor(self.scenario.farm_size_sigma_bra)
            self.base_yield *= self.size_factor
            self.fixed_costs *= self.size_factor

            # Initial price: cost-based at full yield, no disruption
            self.quantity_available = self.base_yield
            if self.quantity_available > 0:
                self.unit_price = (
                    self.fixed_costs / self.quantity_available
                ) * (1.0 + self.margin)

        elif self.role == ROLE_USA:
            self.fixed_costs = self.scenario.fixed_costs_usa_farmer
            self.margin = self.scenario.margin_usa_farmer
            self.base_yield = 100.0

            # same size-factor mechanism as BRA
            self.size_factor = self._sample_size_factor(self.scenario.farm_size_sigma_usa)
            self.base_yield *= self.size_factor
            self.fixed_costs *= self.size_factor

            # initial price: cost-based at full yield, no disruption
            # higher fixed_costs than BRA -> higher unit_price at baseline
            self.quantity_available = self.base_yield
            if self.quantity_available > 0:
                self.unit_price = (
                    self.fixed_costs / self.quantity_available
                ) * (1.0 + self.margin)

        elif self.role == ROLE_ARG:
            self.fixed_costs = self.scenario.fixed_costs_arg_farmer
            self.margin = self.scenario.margin_arg_farmer
            self.base_yield = 100.0 # Placeholder; loaded from data later

            self.size_factor = self._sample_size_factor(self.scenario.farm_size_sigma_arg)
            self.base_yield *= self.size_factor
            self.fixed_costs *= self.size_factor

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
        if self.role == ROLE_BRA:
            self._step_bra()
        elif self.role == ROLE_USA:
            self._step_usa()
        elif self.role == ROLE_ARG:
            self._step_arg()
        elif self.role == ROLE_EU:
            self._step_eu()

    # -------------------------------------------------
    # SA farmer: produce soja, price from fixed costs
    # -------------------------------------------------

    def _step_bra(self):
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
    # USA farmer: produce soja, price from fixed costs - no shock
    # --------------------------------------------------

    def _step_usa(self):
        """
        Produce soja this step.

        USA farmers are not affected by the BRA shock - supply is stable.
        base_yield acts as a hard capacity ceiling.
        There is no mechanism to scale output above it.

        Higher fixed_costs than BRA -> higher baseline unit_price.
        EU wholesalers prefer BRA under normal conditions and switch to USA
        only when BRA prices rise above USA prices under shock.
        """
        surplus_factor = self.scenario.usa_surplus_factor
        self.quantity_available = self.base_yield * surplus_factor  # now offers 150t

        if self.base_yield > 0:
            self.unit_price = (self.fixed_costs / self.base_yield) * (1.0 + self.margin)  # still priced at 100t
        else:
            self.unit_price = 0.0

    # --------------------------------------------------
    # ARG farmer: produce soja, price from fixed costs - no BRA shock
    # --------------------------------------------------

    def _step_arg(self):
        """
        Produce soja this step.

        Argentina farmers are not affected by the BRA shock.

        Unlike USA(surplus_factor for emergency scaling),
        ARG produces at base_yield every step - a permanent baseline supplier.

        farm_capacity_arg allows ARG-specific shocks to be modelled independently.
        Defaults to 1.0 = always unshocked.
        """
        shock_scale = self.model.environment.shock_scale
        farm_capacity = 1.0 + shock_scale * (self.scenario.farm_capacity_arg - 1.0)
        self.quantity_available = self.base_yield * farm_capacity

        if self.quantity_available > 0:
            self.unit_price = (
                self.fixed_costs / self.quantity_available
            ) * (1.0 + self.margin)
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
