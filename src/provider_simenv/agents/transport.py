"""
  role="sa_santos"      Land / port transport: Brazil originator -> Santos export port
  role="sa_paranagua"   Land / port transport: Brazil originator -> Paranagua export port
  role="sea_santos"     Maritime transport: Santos -> EU Port (Rotterdam)
  role="sea_paranagua"  Maritime transport: Paranagua -> EU Port (Hamburg)
  role="sea_arg"        Maritime transport: Argentina originator -> EU Port (Rotterdam)
  role="sea_usa"        Maritime transport: US originator -> EU Port (Rotterdam)
  role="eu_rtm"         Land transport: Rotterdam (sea_santos + sea_arg + sea_usa -> processor)
  role="eu_ham"         Land transport: Hamburg (sea_paranagua -> processor)

Transport agents carry the commodity price through and add a service fee:
  unit_price = upstream_unit_price + (fixed_costs / quantity_moved) * (1 + margin)

Volume routing:
    Brazil soy splits across its declared export ports using entity-keyed shares.
    Argentina and US originators each feed their own sea lane directly.

sea_santos/arg/usa merge at eu_rtm.
sea_paranagua arrives at eu_ham.

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. Model applies the archetype params from topology.py: role, energy
     binding, fixed_costs, capacity, transit_steps.
  3. agent.post_setup() → starts at full capacity with the initial service fee.
"""

import math

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
        """
        Derived initialisation from the archetype params the model applied
        (fixed_costs, capacity, transit_steps): start at full capacity with
        the cost-based initial service fee.
        """
        self.quantity_available = self.capacity
        # Initial service fee at full capacity
        if self.capacity > 0:
            margin = self.scenario.margin_transport
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
            self._move(self.model.upstream("sea_lane_arg"))
        elif self.role == ROLE_SEA_USA:
            self._move(self.model.upstream("sea_lane_usa"))
        elif self.role == ROLE_EU_RTM:
            self._step_eu_rtm()
        elif self.role == ROLE_EU_HAM:
            self._step_eu_ham()

    # ------------------------------------------------------------------
    # Shared helper: receive volume from an upstream AgentList,
    # cap at capacity, compute all-in unit_price (commodity + freight)
    # ------------------------------------------------------------------

    def _move(self, upstream):
        """
        Pull an equal share of upstream output, cap at own capacity,
        and compute the all-in price passed to the next chain node.

        Capacity is scaled by this agent's "capacity" binding slot (the port
        supply shock); roles without that slot run at full capacity (1.0).
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

        effective_factor = self.effective("capacity")

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
            energy_factor = self.effective("energy")
            effective_costs = self.fixed_costs * energy_factor
            freight_fee = (effective_costs / self.quantity_available) * (1.0 + margin)
            self.unit_price = upstream_price + freight_fee
        else:
            self.unit_price = 0.0


    def _route_share(self, list_name: str) -> float:
        """Normalized share for one of an originator's declared port routes."""
        adjacency = self.model._flow_adjacency
        upstream_names = adjacency.get(list_name, ())
        routes: dict[str, str] = {}
        for entry in self.model._roster:
            route_name = entry.archetype.name
            if entry.archetype.agent_class is not Transport:
                continue
            if len(entry.entity_ids) != 1:
                continue
            if adjacency.get(route_name, ()) == upstream_names:
                routes[route_name] = entry.entity_ids[0]

        if list_name not in routes:
            raise ValueError(f"transport route {list_name!r} has no declared port entity")

        explicit: dict[str, float] = {}
        unspecified: list[str] = []
        for route_name, entity_id in routes.items():
            attr = f"share_{entity_id}"
            if not hasattr(self.scenario, attr):
                unspecified.append(route_name)
                continue
            value = float(getattr(self.scenario, attr))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{attr} must be a finite non-negative route weight")
            explicit[route_name] = value

        if len(routes) == 1:
            return 1.0
        if not explicit:
            return 1.0 / len(routes)

        weights = dict(explicit)
        remaining = max(0.0, 1.0 - sum(explicit.values()))
        if unspecified:
            default = remaining / len(unspecified)
            weights.update({route_name: default for route_name in unspecified})

        total = sum(weights.values())
        if total <= 0.0:
            raise ValueError("route weights must have a positive total")
        return weights[list_name] / total


    def _move_split(self, upstream_list, share: float):
        """
        Like _move, but routes only share fraction of total upstream volume through this port.
        Used to split wholesaler output between Santos and Paranagua.

        :param share: fraction of total wholesaler output for this port (e.g. 0.7 for Santos, 0.3 for Paranagua).
        """
        margin = self.scenario.margin_transport
        if hasattr(upstream_list, 'filter'):
            active_upstream = upstream_list.filter(lambda a: a.active)
        else:
            active_upstream = upstream_list
        n_self = len(self._peer_list().filter(lambda a: a.active))

        if not active_upstream or n_self == 0:
            self.quantity_available = 0.0
            self.utilisation = 0.0
            self.unit_price = 0.0
            return

        total_volume = sum(a.quantity_available for a in active_upstream)
        if total_volume <= 0.0:
            self.quantity_available = 0.0
            self.utilisation = 0.0
            self.unit_price = 0.0
            return

        # each agent in this port takes an equal slice of the port's share
        volume_in = (total_volume * share) / n_self

        effective_factor = self.effective("capacity")
        effective_capacity = self.capacity * effective_factor

        self.quantity_available = min(volume_in, effective_capacity)
        self.utilisation = (
            self.quantity_available / effective_capacity if effective_capacity > 0 else 0.0
        )

        total_value = sum(a.unit_price * a.quantity_available for a in active_upstream)
        upstream_price = (total_value / total_volume) if total_volume > 0 else 0.0

        if self.quantity_available > 0:
            energy_factor = self.effective("energy")
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
        Receive soja from the Brazil originator, move to Santos export port.
        Port capacity applied as throughput limit.
        """
        self._move_split(
            self.model.upstream("transport_sa_santos"),
            share=self._route_share("transport_sa_santos"),
        )

    def _step_sa_paranagua(self):
        """
        Receive soja from the Brazil originator, move to Paranagua export port.
        Port capacity applied as throughput limit.
        """
        self._move_split(
            self.model.upstream("transport_sa_paranagua"),
            share=self._route_share("transport_sa_paranagua"),
        )

    def _step_sea_santos(self):
        """
        Ship soja fraom santos export port to EU (Rotterdam)
        """
        self._move(self.model.upstream("sea_lane_santos"))

    def _step_sea_paranagua(self):
        """
        Ship soja from Paranagua export port to EU (Hamburg).
        """
        self._move(self.model.upstream("sea_lane_paranagua"))

    def _step_eu_rtm(self):
        """
        Buy up to Rotterdam's throughput from the cheapest arriving lanes.

        Each upstream lane's quantity_available becomes the volume admitted
        into Rotterdam this step, so losing lanes expose zero admitted flow.
        """
        upstream = self.model.upstream("transport_eu_rtm")
        if hasattr(upstream, "filter"):
            active_upstream = upstream.filter(lambda a: a.active)
        else:
            active_upstream = upstream or []

        effective_capacity = self.capacity * self.effective("capacity")
        demand_target = min(self.capacity, effective_capacity)
        remaining = max(0.0, demand_target)
        purchased_value = 0.0

        for lane in sorted(active_upstream, key=lambda a: a.unit_price):
            admitted = min(max(0.0, lane.quantity_available), remaining)
            lane.quantity_available = admitted
            purchased_value += lane.unit_price * admitted
            remaining -= admitted

        purchased = demand_target - remaining
        self.quantity_available = max(0.0, purchased)
        self.utilisation = (
            self.quantity_available / effective_capacity
            if effective_capacity > 0.0 else 0.0
        )

        if self.quantity_available > 0.0:
            upstream_price = purchased_value / self.quantity_available
            energy_factor = self.effective("energy")
            effective_costs = self.fixed_costs * energy_factor
            freight_fee = (
                effective_costs / self.quantity_available
            ) * (1.0 + self.scenario.margin_transport)
            self.unit_price = upstream_price + freight_fee
        else:
            self.unit_price = 0.0


    def _step_eu_ham(self):
        """
        Hamburg EU entry point.
        Receives soja from Paranagua sea lane only.
        Port capacity shock (port_capacity_hamburg) applied here.
        """
        self._move(self.model.upstream("transport_eu_ham"))

