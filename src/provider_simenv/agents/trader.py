"""
agents/trader.py — Pure intermediary / trading actors.

  role="wholesaler"   Aggregates soja from BRA + USA farmers (greedy cheapest first)
                      price = (input_cost + fixed_costs/stock) * (1 + margin)

  role="feed_trader"  Distributes feed to EU livestock farmers.
                      price = (input_cost + fixed_costs/stock) * (1 + margin)

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. agent.role = …    → Model assigns the role.
  3. agent.post_setup() → Reads fixed_costs/margin from scenario.
"""

from .base import SupplyChainAgent

ROLE_WHOLESALER = "wholesaler"
ROLE_FEED_TRADER = "feed_trader"


class Trader(SupplyChainAgent):
    """
    Pure intermediary — soja wholesaler or feed distributor.

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

        # volume sourced from each origin this step
        self.bra_volume: float = 0.0
        self.arg_volume: float = 0.0
        self.usa_volume: float = 0.0

        # storage capacity and utilisation (wholesaler only)
        self.storage_capacity: float = 0.0
        self.storage_utilization: float = 0.0   # stock / storage_capacity

    def post_setup(self):
        """Role-specific initialisation."""
        if self.role == ROLE_WHOLESALER:
            self.fixed_costs = self.scenario.fixed_costs_wholesaler
            self.margin = self.scenario.margin_wholesaler
            self.markup = self.margin
            self.storage_capacity = self.scenario.wholesaler_storage_capacity
            self.stock = 0.0
            self.quantity_available = 0.0
            self.unit_price = 0.0
            self.storage_utilization = 0.0

        elif self.role == ROLE_FEED_TRADER:
            self.fixed_costs = self.scenario.fixed_costs_feed_trader
            self.margin = self.scenario.margin_feed_trader
            self.markup = self.margin
            self.stock = 0.0
            self.quantity_available = 0.0
            self.unit_price = 0.0

    def step(self):
        if not self.active:
            return
        if self.role == ROLE_WHOLESALER:
            self._step_wholesaler()
        elif self.role == ROLE_FEED_TRADER:
            self._step_feed_trader()

    # ------------------------------------------------------------------
    # Wholesaler: greedy cheapest first across BRA + USA farmers
    # ------------------------------------------------------------------

    def _step_wholesaler(self):
        """
        Pool BRA + ARG + USA farmer output and fill this wholesaler's stock
        allocation greedily from the cheapest source first.

        Workflow:
            1. Pool all active BRA + ARG + USA farmers into one list.
            2. Each wholesaler's stock = total_supply / n_wholesalers
                (push model - all supply flows forward)
            3. Sort pooled farmers by unit_price ascending.
            4. Walk cheapest-first: take each farmer's share
                (farmer.quantity_available / n_wholesalers) until
                this wholesaler's allocation is filled.
            5. avg_input_price = quantity-weighted cost of what was taken.

        Emergent switching:
        Under a BRA shock, BRA unit_price rises above USA unit_price ->
        USA sorts to the front ->
        wholesaler fills from USA first ->
        lower average input cost propagates downstream automatically.
        """

        active_bra = self.model.bra_farmers.filter(lambda f: f.active)
        active_arg = self.model.arg_farmers.filter(lambda f: f.active)
        active_usa = self.model.usa_farmers.filter(lambda f: f.active)
        all_farmers = active_bra + active_arg + active_usa
        n_wholesalers = len(self.model.wholesalers.filter(lambda w: w.active))

        if not all_farmers or n_wholesalers == 0:
            self.stock = 0.0
            self.quantity_available = 0.0
            self.unit_price = 0.0
            self.bra_volume = 0.0
            self.arg_volume = 0.0
            self.usa_volume = 0.0
            return

        # Demand target: based on unshocked capacity, not current disrupted supply
        # Under no shock: demand == old push share
        # Under BRA shock: demand stays the same -> wholesaler actively pulls more from USA
        normal_capacity = ( sum(f.base_yield for f in active_bra) + sum(f.base_yield for f in active_arg) + sum(f.base_yield for f in active_usa))
        my_demand = min(normal_capacity / n_wholesalers, self.storage_capacity)

        # Greedy fill: pull from cheapest source first, up to each farmer's
        # available allocation (farmer.quantity_available / n_wholesalers)
        # USA farmers expose surplus capacity via quantity_available > base_yield,
        # so wholesalers can pull more from USA when BRA is expensive.
        sorted_farmers = sorted(all_farmers, key=lambda f: f.unit_price)
        remaining = my_demand
        total_cost = 0.0
        bra_taken = 0.0
        arg_taken = 0.0
        usa_taken = 0.0
        for farmer in sorted_farmers:
            if remaining <= 0.0:
                break
            farmer_alloc = farmer.quantity_available / n_wholesalers
            taken = min(farmer_alloc, remaining)
            total_cost += taken * farmer.unit_price
            remaining -= taken
            if farmer.role == "bra":
                bra_taken += taken
            elif farmer.role == "arg":
                arg_taken += taken
            else:
                usa_taken += taken

        actual_taken = bra_taken + arg_taken + usa_taken
        self.bra_volume = bra_taken
        self.arg_volume = arg_taken
        self.usa_volume = usa_taken
        self.stock = actual_taken
        self.quantity_available = actual_taken
        self.storage_utilization = (actual_taken / self.storage_capacity if self.storage_capacity > 0 else 0.0)

        avg_input_price = total_cost / actual_taken if actual_taken > 0 else 0.0

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
        manufacturers = self.model.feed_manufacturers.filter(lambda m: m.active)
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
