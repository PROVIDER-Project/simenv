"""
  role="sa_santos"      Land / port transport: wholesalers (BRA+USA) -> Santos export port
  role="sa_paranagua"   Land / port transport: wholesalers (BRA+USA) -> Paranagua export port
  role="sea_santos"     Maritime transport: Santos -> EU Port (Rotterdam)
  role="sea_paranagua"  Maritime transport: Paranagua -> EU Port (Hamburg)
  role="sea_arg"        Maritime transport: ARG wholesalers -> EU Port (Rotterdam)
                        Bypasses SA land transport
  role="eu_rtm"         Land transport: Rotterdam (sea_santos + sea_arg + sea_usa -> processor)
  role="eu_ham"         Land transport: Hamburg (sea_paranagua -> processor)

Transport agents carry the commodity price through and add a service fee:
  unit_price = upstream_unit_price + (fixed_costs / quantity_moved) * (1 + margin)

Volume routing:
    BRA + USA soy:
        wholesaler (BRA + USA volume) * santos_share -> transport_sa_santos -> sea_lane_santos
        wholesaler (BRA + USA volume) * (1 - santos_share) -> transport_sa_paranagua -> sea_lane_paranagua
    ARG soy:
        wholesaler arg_volume -> sea_lane_arg (direct, no SA land transport)

sea_santos/arg/usa merge at eu_rtm.
sea_paranagua arrives at eu_ham.

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. agent.role = …    → Model assigns the role.
  3. agent.post_setup() → Reads fixed_costs from scenario, sets capacity.
"""

from .base import SupplyChainAgent

ROLE_SA_SANTOS = "sa_santos"
ROLE_SA_PARANAGUA = "sa_paranagua"
ROLE_SEA_SANTOS = "sea_santos"
ROLE_SEA_PARANAGUA = "sea_paranagua"
ROLE_SEA_ARG = "sea_arg"
ROLE_EU_RTM = "eu_rtm"
ROLE_EU_HAM = "eu_ham"
ROLE_SEA_USA = "sea_usa"


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

        if self.role in (ROLE_SA_SANTOS, ROLE_SA_PARANAGUA):
            self.fixed_costs = self.scenario.fixed_costs_transport_sa
            self.capacity = 500.0

        elif self.role in (ROLE_SEA_SANTOS, ROLE_SEA_PARANAGUA, ROLE_SEA_ARG, ROLE_SEA_USA):
            self.fixed_costs = self.scenario.fixed_costs_transport_sea
            self.capacity = 1000.0
            self.transit_steps = 4      # ~4-week Atlantic crossing

        elif self.role in (ROLE_EU_RTM, ROLE_EU_HAM):
            self.fixed_costs = self.scenario.fixed_costs_transport_eu
            self.capacity = 500.0

        self.quantity_available = self.capacity
        # Initial service fee at full capacity
        if self.capacity > 0:
            self.unit_price = (self.fixed_costs / self.capacity) * (1.0 + margin)

    def step(self):
        if not self.active:
            return
        if self.role == ROLE_SA_SANTOS:
            self._step_sa_santos()
        elif self.role == ROLE_SA_PARANAGUA:
            self._step_sa_paranagua()
        elif self.role == ROLE_SEA_SANTOS:
            self._step_sea_santos()
        elif self.role == ROLE_SEA_PARANAGUA:
            self._step_sea_paranagua()
        elif self.role == ROLE_SEA_ARG:
            self._step_sea_arg()
        elif self.role == ROLE_SEA_USA:
            self._step_sea_usa()
        elif self.role == ROLE_EU_RTM:
            self._step_eu_rtm()
        elif self.role == ROLE_EU_HAM:
            self._step_eu_ham()

    # ------------------------------------------------------------------
    # Shared helper: receive volume from an upstream AgentList,
    # cap at capacity, compute all-in unit_price (commodity + freight)
    # ------------------------------------------------------------------

    def _move(self, upstream, shock_key: tuple[str, str] | None = None):
        """
        Pull an equal share of upstream output, ca at own capacity,
        and compute the all-in price passed to the next chain node.

        shock_key: PDL (entity, field) whoe effective value scales this agent's capacity
        """
        margin = self.scenario.margin_transport

        if hasattr(upstream, 'filter'):
            active_upstream = upstream.filter(lambda a: a.active)
        else:
            active_upstream = upstream

        n_self = len(self._peer_list().filter(lambda a: a.active))

        if not active_upstream or n_self == 0:
            self.quantity_available = 0.0
            self.utilisation = 0.0
            self.unit_price = 0.0
            return

        total_volume = sum(a.quantity_available for a in active_upstream)
        volume_in = total_volume / n_self

        env = self.model.environment
        effective_factor = env.get_effective_value(*shock_key) if shock_key else 1.0

        # effective capacity after applying port capacity shock
        effective_capacity = self.capacity * effective_factor

        # cap at effective capacity
        self.quantity_available = min(volume_in, effective_capacity)
        self.utilisation = (self.quantity_available / effective_capacity if effective_capacity > 0 else 0.0)

        # weighted average commodity price from upstream
        total_value = sum(a.unit_price * a.quantity_available for a in active_upstream)
        upstream_price = (total_value / total_volume) if total_volume > 0 else 0.0

        # price = commodity price + freight fee per unit
        # energy price factor raises transport operation costs
        if self.quantity_available > 0:
            energy_factor = env.get_effective_value("gas_supply", "price")
            effective_costs = self.fixed_costs * energy_factor
            freight_fee = (effective_costs / self.quantity_available) * (1.0 + margin)
            self.unit_price = upstream_price + freight_fee
        else:
            self.unit_price = 0.0


    def _move_split(self, upstream_list, share: float, shock_key: tuple[str, str] | None = None, origins: set[str] | None = None):
        """
        Like _move, but routes only share fraction of total upstream volume through this port.
        Used to split wholesaler output between Santos and Paranagua.

        :param origins: allow-list of origin tags to carry (e.g. {"bra"}). Each tag t reads the upstream t_volume field. None = carry all origins (full volume)
        :param shock_key: PDL (entity, field) whose effective value scales this agent's capacity
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
        if origins is None:
            routable_volume = total_volume
        else:
            routable_volume = sum(
                getattr(a, f"{origin}_volume", 0.0)
                for a in active_upstream
                for origin in origins
            )

        if routable_volume <= 0.0:
            self.quantity_available = 0.0
            self.utilisation = 0.0
            self.unit_price = 0.0
            return

        # each agent in this port takes an equal slice of the port's share
        volume_in = (routable_volume * share) / n_self

        env = self.model.environment
        effective_factor = env.get_effective_value(*shock_key) if shock_key else 1.0
        effective_capacity = self.capacity * effective_factor

        self.quantity_available = min(volume_in, effective_capacity)
        self.utilisation = (
            self.quantity_available / effective_capacity if effective_capacity > 0 else 0.0
        )

        total_value = sum(a.unit_price * a.quantity_available for a in active_upstream)
        upstream_price = (total_value / total_volume) if total_volume > 0 else 0.0

        if self.quantity_available > 0:
            energy_factor = env.get_effective_value("gas_supply", "price")
            effective_costs = self.fixed_costs * energy_factor
            freight_fee = (effective_costs / self.quantity_available) * (1.0 + margin)
            self.unit_price = upstream_price + freight_fee
        else:
            self.unit_price = 0.0


    def _peer_list(self):
        """Return the AgentList this agent belongs to (for peer count)."""
        if self.role == ROLE_SA_SANTOS:
            return self.model.transport_sa_santos
        elif self.role == ROLE_SA_PARANAGUA:
            return self.model.transport_sa_paranagua
        elif self.role == ROLE_SEA_SANTOS:
            return self.model.sea_lane_santos
        elif self.role == ROLE_SEA_PARANAGUA:
            return self.model.sea_lane_paranagua
        elif self.role == ROLE_SEA_ARG:
            return self.model.sea_lane_arg
        elif self.role == ROLE_SEA_USA:
            return self.model.sea_lane_usa
        elif self.role == ROLE_EU_RTM:
            return self.model.transport_eu_rtm
        elif self.role == ROLE_EU_HAM:
            return self.model.transport_eu_ham
        raise ValueError(f"Unknown transport role: {self.role!r}")

    # ----------------------------
    # Role-specific step methods
    # ----------------------------

    def _step_sa_santos(self):
        """
        Receive soja from wholesalers, move to Santos export port.
        Port capacity applied as throughput limit.
        """
        self._move_split(
            self.model.wholesalers,
            share=self.scenario.santos_share,
            shock_key=("santos_port", "supply"),
            origins={"bra"},
        )

    def _step_sa_paranagua(self):
        """
        Receive soja from wholesalers, move to Paranagua export port.
        Port capacity applied as throughput limit.
        """
        self._move_split(
            self.model.wholesalers,
            share=1.0 - self.scenario.santos_share,
            shock_key=("paranagua_port", "supply"),
            origins={"bra"},
        )

    def _step_sea_santos(self):
        """
        Ship soja fraom santos export port to EU (Rotterdam)
        """
        self._move(self.model.transport_sa_santos)

    def _step_sea_paranagua(self):
        """
        Ship soja from Paranagua export port to EU (Hamburg).
        """
        self._move(self.model.transport_sa_paranagua)

    def _step_sea_arg(self):
        """
        Route ARG-origin soja directly from wholesalers to EU port (Rotterdam).

        Bypasses SA land transport entirely
        Volume = sum of wholesaler.arg_volume across all active wholesalers.
        Price = wholesaler avg. price applied to ARG-origin portion.
        """
        margin = self.scenario.margin_transport
        active_w = self.model.wholesalers.filter(lambda w: w.active)
        n_self = len(self.model.sea_lane_arg.filter(lambda a: a.active))

        if not active_w or n_self == 0:
            self.quantity_available = 0.0
            self.utilisation = 0.0
            self.unit_price = 0.0
            return

        total_arg = sum(w.arg_volume for w in active_w)
        if total_arg <= 0.0:
            self.quantity_available = 0.0
            self.utilisation = 0.0
            self.unit_price = 0.0
            return

        volume_in = total_arg / n_self

        # ARG ports not shocked in current scenarios
        # capacity_factor=1.0. A future KG param (port_capacity_arg) can be wired in here.
        effective_capacity = self.capacity

        self.quantity_available = min(volume_in, effective_capacity)
        self.utilisation = (
            self.quantity_available / effective_capacity if effective_capacity > 0 else 0.0
        )

        # upstream price: wholesaler unit_price weighted by each wholesaler's arg_volume
        total_value = sum(w.unit_price * w.arg_volume for w in active_w)
        upstream_price = total_value / total_arg

        if self.quantity_available > 0:
            energy_factor = self.model.environment.get_effective_value("gas_supply", "price")
            effective_costs = self.fixed_costs * energy_factor
            freight_fee = (effective_costs / self.quantity_available) * (1.0 + margin)
            self.unit_price = upstream_price + freight_fee
        else:
            self.unit_price = 0.0


    def _step_sea_usa(self):
        """
        Route USA-origin soja directly from wholesalers to EU port (Rotterdam).

        Bypasses SA land transport entirely - US soy exits via Gulf Coast ports (New Orleans, Houston)
        Volume = sum of wholesaler.arg_volume across all active wholesalers.
        Price = wholesaler avg. price applied to USA-origin portion.
        """
        margin = self.scenario.margin_transport
        active_w = self.model.wholesalers.filter(lambda w: w.active)
        n_self = len(self.model.sea_lane_usa.filter(lambda a: a.active))

        if not active_w or n_self == 0:
            self.quantity_available = 0.0
            self.utilisation = 0.0
            self.unit_price = 0.0
            return

        total_usa = sum(w.usa_volume for w in active_w)
        if total_usa <= 0.0:
            self.quantity_available = 0.0
            self.utilisation = 0.0
            self.unit_price = 0.0
            return

        volume_in = total_usa / n_self

        # USA Gulf ports not shocked in current scenarios - capacity_factor = 1.0
        # Future KG param (port_capacity_us_gulf) can be wired in.
        effective_capacity = self.capacity

        self.quantity_available = min(volume_in, effective_capacity)
        self.utilisation = (
            self.quantity_available / effective_capacity if effective_capacity > 0 else 0.0
        )

        # Upstream price: wholesaler unit_price weighted by each wholesaler's usa_volume
        total_value = sum(w.unit_price * w.usa_volume for w in active_w)
        upstream_price = total_value / total_usa

        if self.quantity_available > 0:
            energy_factor = self.model.environment.get_effective_value("gas_supply", "price")
            effective_costs = self.fixed_costs * energy_factor
            freight_fee = (effective_costs / self.quantity_available) * (1.0 + margin)
            self.unit_price = upstream_price + freight_fee
        else:
            self.unit_price = 0.0

    def _step_eu_rtm(self):
        """
        Rotterdam EU entry point.
        Receives soja from Santos sea lan, ARG direct, and USA direct.
        Port capacity shock (port_capacity_rotterdam) applied here.
        """
        combined = (
            self.model.sea_lane_santos.filter(lambda a: a.active)
            + self.model.sea_lane_arg.filter(lambda a: a.active)
            + self.model.sea_lane_usa.filter(lambda a: a.active)
        )
        self._move(combined, shock_key=("rotterdam_port", "supply"))


    def _step_eu_ham(self):
        """
        Hamburg EU entry point.
        Receives soja from Paranagua sea lane only.
        Port capacity shock (port_capacity_hamburg) applied here.
        """
        self._move(
            self.model.sea_lane_paranagua,
            shock_key=("hamburg_port", "supply"),
        )

