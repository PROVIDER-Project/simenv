"""
  role="sa_land"  Land transport SA farms → SA export port.
  role="sea"      Maritime transport SA port → EU port.
  role="eu_land"  Land transport EU port → processing plants.

Transport agents carry the commodity price through and add a service fee:
  unit_price = upstream_unit_price + (fixed_costs / quantity_moved) * (1 + margin)

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. agent.role = …    → Model assigns the role.
  3. agent.post_setup() → Reads fixed_costs from scenario, sets capacity.
"""

from .base import SupplyChainAgent

ROLE_SA_LAND = "sa_land"
ROLE_SEA = "sea"
ROLE_EU_LAND = "eu_land"


class Transport(SupplyChainAgent):
    """
    Capacity-constrained transport operator.

    Shared state:
      role                   "sa_land", "sea", or "eu_land".
      fixed_costs            Operating cost per step (EUR/step).
      capacity               Maximum units movable per step (tonnes).
      utilisation            Fraction of capacity used this step (0–1).
      utilisation_threshold  Threshold above which unit_price rises (future).

    Sea-specific state:
      transit_steps  Steps for cargo to cross SA → EU port (0 for land).
    """

    def setup(self):
        super().setup()
        self.role: str = ""
        self.fixed_costs: float = 0.0
        self.capacity: float = 0.0
        self.utilisation: float = 0.0
        self.utilisation_threshold: float = 0.8
        self.transit_steps: int = 0

    def post_setup(self):
        margin = self.scenario.margin_transport

        if self.role == ROLE_SA_LAND:
            self.fixed_costs = self.scenario.fixed_costs_transport_sa
            self.capacity = 500.0

        elif self.role == ROLE_SEA:
            self.fixed_costs = self.scenario.fixed_costs_transport_sea
            self.capacity = 1000.0
            self.transit_steps = 4      # ~4-week Atlantic crossing

        elif self.role == ROLE_EU_LAND:
            self.fixed_costs = self.scenario.fixed_costs_transport_eu
            self.capacity = 500.0

        self.quantity_available = self.capacity
        # Initial service fee at full capacity
        if self.capacity > 0:
            self.unit_price = (self.fixed_costs / self.capacity) * (1.0 + margin)

    def step(self):
        if not self.active:
            return
        if self.role == ROLE_SA_LAND:
            self._step_sa_land()
        elif self.role == ROLE_SEA:
            self._step_sea()
        elif self.role == ROLE_EU_LAND:
            self._step_eu_land()

    # ------------------------------------------------------------------
    # Shared helper: receive volume from an upstream AgentList,
    # cap at capacity, compute all-in unit_price (commodity + freight)
    # ------------------------------------------------------------------

    def _move(self, upstream_list, capacity_factor: float = 1.0):
        """
        Pull an equal share of upstream output, ca at own capacity,
        and compute the all-in price passed to the next chain node.

        capacity_factor: optional multiplier on self.capacity (used to
        apply port_capacity_sa for SA land transport).
        """
        margin = self.scenario.margin_transport
        active_upstream = upstream_list.filter(lambda a: a.active)
        n_self = len(self._peer_list().filter(lambda a: a.active))

        if not active_upstream or n_self == 0:
            self.quantity_available = 0.0
            self.utilisation = 0.0
            self.unit_price = 0.0
            return

        total_volume = sum(a.quantity_available for a in active_upstream)
        volume_in = total_volume / n_self

        shock_scale = self.model.environment.shock_scale
        effective_factor = 1.0 + shock_scale * (capacity_factor - 1.0)

        # effective capacity after applying port capacity shock
        effective_capacity = self.capacity * effective_factor

        # cap at effective capacity
        self.quantity_available = min(volume_in, effective_capacity)
        self.utilisation = (self.quantity_available * effective_capacity if effective_capacity > 0 else 0.0)

        # weighted average commodity price from upstream
        total_value = sum(a.unit_price * a.quantity_available for a in active_upstream)
        upstream_price = (total_value / total_volume) if total_volume > 0 else 0.0

        # price = commodity price + freight fee per unit
        # energy price factor raises transport operation costs
        if self.quantity_available > 0:
            energy_factor = 1.0 + shock_scale * (self.scenario.energy_price_factor - 1.0)
            effective_costs = self.fixed_costs * energy_factor
            freight_fee = (effective_costs / self.quantity_available) * (1.0 + margin)
            self.unit_price = upstream_price + freight_fee
        else:
            self.unit_price = 0.0

    def _peer_list(self):
        """Return the AgentList this agent belongs to (for peer count)."""
        if self.role == ROLE_SA_LAND:
            return self.model.transport_sa
        elif self.role == ROLE_SEA:
            return self.model.sea_transport
        elif self.role == ROLE_EU_LAND:
            return self.model.transport_eu
        raise ValueError(f"Unknown transport role: {self.role!r}")

    # ----------------------------
    # Role-specific step methods
    # ----------------------------

    def _step_sa_land(self):
        """
        Receive soja from wholesalers, move to SA export port.
        Port capacity applied as throughput limit.
        """
        self._move(self.model.wholesalers, capacity_factor=self.scenario.port_capacity_sa)

    def _step_sea(self):
        """Receive soja from SA land transport, ship to EU port."""
        self._move(self.model.transport_sa)

    def _step_eu_land(self):
        """Receive soja from sea transport, deliver to processors."""
        self._move(self.model.sea_transport)
