"""
agents/trader.py — Trading actors.

  role="wholesaler"   Aggregates soja from one producing region
                      price = (input_cost + fixed_costs/stock) * (1 + margin)

  role="feed_trader"  Distributes feed to EU livestock farmers.
                      price = (input_cost + fixed_costs/stock) * (1 + margin)

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. Model applies the archetype params from topology.py: role, fixed_costs,
     margin, storage_capacity (wholesaler).
  3. agent.post_setup() → aliases markup, resets per-step flow state.
"""

from .base import SupplyChainAgent

ROLE_WHOLESALER = "wholesaler"
ROLE_FEED_TRADER = "feed_trader"


class Trader(SupplyChainAgent):
    """
    Soja originator or feed distributor.

    Shared state:
      role         "wholesaler" or "feed_trader".
      fixed_costs  Operating cost per step (EUR/step).
      margin       Profit ratio applied on top of per-unit cost.
      stock        Inventory of the traded commodity this step (tonnes).
    """

    def setup(self):
        super().setup()
        self.role: str = ""
        self.fixed_costs: float = 0.0
        self.markup: float = 0.0        # kept as alias; set equal to margin
        self.margin: float = 0.0
        self.stock: float = 0.0

        # storage capacity and utilisation (wholesaler only)
        self.storage_capacity: float = 0.0
        self.storage_utilization: float = 0.0   # stock / storage_capacity

    def post_setup(self):
        """
        Derived initialisation from the archetype params the model applied
        (fixed_costs, margin; storage_capacity for wholesalers): alias the
        markup and reset per-step flow state.
        """
        self.markup = self.margin
        self.stock = 0.0
        self.quantity_available = 0.0
        self.unit_price = 0.0
        self.storage_utilization = 0.0

    def step(self):
        if not self.active:
            return
        if self.role == ROLE_WHOLESALER:
            self._step_wholesaler()
        elif self.role == ROLE_FEED_TRADER:
            self._step_feed_trader()

    # ------------------------------------------------------------------
    # Wholesaler: regional aggregation
    # ------------------------------------------------------------------

    def _step_wholesaler(self):
        """
        Aggregate the output of this originator's own upstream farmers.
        """

        list_name = self.origin
        if not list_name:
            list_name = next(
                entry.archetype.name
                for entry in self.model._roster
                if entry.archetype.role == ROLE_WHOLESALER
                and any(
                    agent is self
                    for agent in getattr(self.model, entry.archetype.name).agents
                )
            )

        farmers = self.model.upstream(list_name)
        peers = getattr(self.model, list_name)
        n_wholesalers = len(peers.filter(lambda w: w.active))

        if not farmers or n_wholesalers == 0:
            self.stock = 0.0
            self.quantity_available = 0.0
            self.unit_price = 0.0
            self.storage_utilization = 0.0
            return

        normal_capacity = sum(f.base_yield for f in farmers)
        current_supply = sum(f.quantity_available for f in farmers)
        normal_share = normal_capacity / n_wholesalers
        current_share = current_supply / n_wholesalers
        my_demand = min(
            max(normal_share, current_share),
            self.storage_capacity,
        )
        actual_taken = min(current_share, my_demand)

        self.stock = actual_taken
        self.quantity_available = actual_taken
        self.storage_utilization = (actual_taken / self.storage_capacity if self.storage_capacity > 0 else 0.0)

        total_value = sum(f.unit_price * f.quantity_available for f in farmers)
        avg_input_price = total_value / current_supply if current_supply > 0 else 0.0

        if self.stock > 0:
            cost_per_unit = avg_input_price + self.fixed_costs / self.stock
            self.unit_price = cost_per_unit * (1.0 + self.margin)
        else:
            self.unit_price = 0.0

    # ------------------------------------------------------------------
    # Feed trader: collect feed from manufacturers, distribute to EU farmers
    # ------------------------------------------------------------------

    def _step_feed_trader(self):
        """
        Collect an equal share of all feed manufacturer output.
        Price = (input_price + fixed_costs/stock) * (1 + margin).
        EU farmers then read from self.model.feed_traders in their step().
        """
        manufacturers = self.model.upstream("feed_traders")
        n_traders = len(self.model.feed_traders.filter(lambda t: t.active))

        if not manufacturers or n_traders == 0:
            self.stock = 0.0
            self.quantity_available = 0.0
            return

        total_feed = sum(m.quantity_available for m in manufacturers)
        self.stock = total_feed / n_traders

        # Weighted average price paid to feed manufacturers
        total_value = sum(
            m.unit_price * m.quantity_available for m in manufacturers
        )
        avg_input_price = (total_value / total_feed) if total_feed > 0 else 0.0

        self.quantity_available = self.stock

        if self.stock > 0:
            cost_per_unit = avg_input_price + self.fixed_costs / self.stock
            self.unit_price = cost_per_unit * (1.0 + self.margin)
        else:
            self.unit_price = 0.0
