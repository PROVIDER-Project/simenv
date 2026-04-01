"""
agents/trader.py — Pure intermediary / trading actors.

  role="wholesaler"   Aggregates soja from SA farmers, sells internationally.
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

    def post_setup(self):
        """Role-specific initialisation."""
        if self.role == ROLE_WHOLESALER:
            self.fixed_costs = self.scenario.fixed_costs_wholesaler
            self.margin = self.scenario.margin_wholesaler
            self.markup = self.margin
            self.stock = 0.0
            self.quantity_available = 0.0
            self.unit_price = 0.0

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
    # Wholesaler: aggregate soja from SA farmers, price and sell on
    # ------------------------------------------------------------------

    def _step_wholesaler(self):
        """
        Collect an equal share of all SA farmer output.
        Price = (weighted avg input price + fixed_costs/stock) * (1 + margin).
        """
        sa_farmers = self.model.sa_farmers.filter(lambda f: f.active)
        n_wholesalers = len(self.model.wholesalers.filter(lambda w: w.active))

        if not sa_farmers or n_wholesalers == 0:
            self.stock = 0.0
            self.quantity_available = 0.0
            return

        total_soja = sum(f.quantity_available for f in sa_farmers)

        # equal share for now
        self.stock = total_soja / n_wholesalers

        # Weighted average price paid to farmers
        total_value = sum(f.unit_price * f.quantity_available for f in sa_farmers)
        avg_input_price = (total_value / total_soja) if total_soja > 0 else 0.0

        self.quantity_available = self.stock

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
