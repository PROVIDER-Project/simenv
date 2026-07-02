"""
  role="processor"         Crusher: raw soja → soja meal (ratio 0.8).
  role="feed_manufacturer" Compounder: soja meal → compound feed (ratio 1.0).

Price logic accounts for the yield loss in conversion:
  To produce 1 unit of output you need (1 / conversion_ratio) units of input.
  unit_price = (input_price / conversion_ratio + fixed_costs / qty) * (1 + margin)

  At the end, a Processor needs to recover:
  1. the cost of its input (e.g. cost of the soja it bought)
  2. its own fixed costs
  3. its margin

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. Model applies the archetype params from topology.py: role, fixed_costs,
     margin, conversion_ratio.
  3. agent.post_setup() → resets per-step flow state.
"""

from .base import SupplyChainAgent

ROLE_PROCESSOR = "processor"
ROLE_FEED_MANUFACTURER = "feed_manufacturer"

class Process(SupplyChainAgent):
    """
    Input-transformation agent — crusher or feed manufacturer.

    Shared state:
      role              "processor" or "feed_manufacturer".
      fixed_costs       Operating cost per step (EUR/step).
      margin            Profit ratio applied on top of per-unit cost.
      input_received    Tonnes of input commodity received this step.
      conversion_ratio  Output units produced per input unit.
    """

    def setup(self):
        super().setup()
        self.role: str = ""
        self.fixed_costs: float = 0.0
        self.margin: float = 0.0
        self.input_received: float = 0.0
        self.conversion_ratio: float = 1.0

    def post_setup(self):
        """
        Derived initialisation from the archetype params the model applied
        (fixed_costs, margin, conversion_ratio): reset per-step flow state.
        """
        self.input_received = 0.0
        self.quantity_available = 0.0
        self.unit_price = 0.0

    def step(self):
        if not self.active:
            return
        if self.role == ROLE_PROCESSOR:
            self._step_processor()
        elif self.role == ROLE_FEED_MANUFACTURER:
            self._step_feed_manufacturer()

    # ------------------------------------------------------------------
    # Shared helper: receive from upstream list, convert, compute price
    # ------------------------------------------------------------------

    def _process(self, upstream_list, peer_list):
        """
        Pull an equal share of upstream output, apply conversion_ratio,
        and compute unit_price accounting for yield loss.

        Output is scaled by this agent's "capacity" binding slot, modelling
        indirect capacity reduction from upstream shortage.

        For every 1 unit of output, (1 / conversion_ratio) input units
        were consumed, so the input cost per output unit is:
            input_price / conversion_ratio
        """
        if hasattr(upstream_list, 'filter'):
            active_upstream = upstream_list.filter(lambda a: a.active)
        else:
            active_upstream = upstream_list
        n_peers = len(peer_list.filter(lambda a: a.active))

        if not active_upstream or n_peers == 0:
            self.input_received = 0.0
            self.quantity_available = 0.0
            self.unit_price = 0.0
            return

        effective_factor = self.effective("capacity")

        total_input = sum(a.quantity_available for a in active_upstream)

        # equal split between processors
        self.input_received = total_input / n_peers

        # output from each processor
        self.quantity_available = self.input_received * self.conversion_ratio * effective_factor

        # Weighted average price of the input commodity
        total_value = sum(
            a.unit_price * a.quantity_available for a in active_upstream
        )
        avg_input_price = (total_value / total_input) if total_input > 0 else 0.0

        if self.quantity_available > 0:
            # Cost per output unit = input cost adjusted for yield + fixed overhead
            input_cost_per_output = avg_input_price / self.conversion_ratio
            fixed_cost_per_unit = self.fixed_costs / self.quantity_available
            self.unit_price = (
                input_cost_per_output + fixed_cost_per_unit
            ) * (1.0 + self.margin)
        else:
            self.unit_price = 0.0

    # --------------------------
    # Role-specific step methods
    # --------------------------

    def _step_processor(self):
        """Receive soja from both EU entry ports (RTM + HAM), crush to meal.
        oil_mill_capacity applied as indirect capacity constraint."""
        self._process(
            upstream_list=self.model.upstream("processors"),
            peer_list=self.model.processors,
        )

    def _step_feed_manufacturer(self):
        """Receive soja meal from processors, compound to animal feed."""
        self._process(
            upstream_list=self.model.upstream("feed_manufacturers"),
            peer_list=self.model.feed_manufacturers,
        )
