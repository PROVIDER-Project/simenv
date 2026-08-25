"""
Transport agents represent declared land nodes and derived sea crossings.

Transport agents carry the commodity price through and add a service fee:
  unit_price = upstream_unit_price + (fixed_costs / quantity_moved) * (1 + margin)

Volume routing:
    Export routes split an originator's volume using entity-keyed shares.
    Sea lanes move the output available at their derived upstream endpoint.
    Single-source import routes move normally; multi-source routes buy cheapest first.

Lifecycle:
  1. setup_agents(n)   → setup() zero-initialises all fields.
  2. Model applies the archetype params from topology.py: role, energy
     binding, fixed_costs, capacity, transit_steps.
  3. agent.post_setup() → starts at full capacity with the initial service fee.
"""

import math

from .base import SupplyChainAgent

ROLE_LAND_TRANSPORT = "land_transport"
ROLE_SEA_LANE = "sea_lane"

class Transport(SupplyChainAgent):
    """
    Capacity-constrained transport operator.

    Shared state:
      role                   "land_transport" or "sea_lane".
      fixed_costs            Operating cost per step (EUR/step).
      capacity               Maximum units movable per step (tonnes).
      utilisation            Fraction of capacity used this step (0–1).
      utilisation_threshold  Threshold above which unit_price rises (future).

    Sea-specific state:
      transit_steps  Steps for cargo to cross between regions (0 for land).
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
        if self.role == ROLE_LAND_TRANSPORT:
            self._step_land_transport()
        elif self.role == ROLE_SEA_LANE:
            self._move(self.model.upstream(self.list_name))
        else:
            raise ValueError(f"Transport has unknown role: {self.role!r}")

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
        Used when one originator supplies multiple export routes.

        :param share: fraction of total originator output for this route.
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
        return getattr(self.model, self.list_name)

    def _feeds_sea_lane(self) -> bool:
        """Whether this transport route supplies a sea-lane list."""
        role_by_name = {
            entry.archetype.name: entry.archetype.role
            for entry in self.model._roster
        }
        return any(
            role_by_name.get(destination) == ROLE_SEA_LANE
            and self.list_name in sources
            for destination, sources in self.model._flow_adjacency.items()
        )

    def _step_land_transport(self):
        """Select land-route behavior from the derived flow graph."""
        upstream_names = self.model._flow_adjacency.get(self.list_name, ())
        upstream = self.model.upstream(self.list_name)
        if self._feeds_sea_lane():
            self._move_split(
                upstream,
                share=self._route_share(self.list_name),
            )
        elif len(upstream_names) > 1:
            self._admit_cheapest(upstream)
        else:
            self._move(upstream)

    def _admit_cheapest(self, upstream):
        """Buy up to this route's throughput from its cheapest upstream actors."""
        if hasattr(upstream, "filter"):
            active_upstream = upstream.filter(lambda a: a.active)
        else:
            active_upstream = upstream or []

        effective_capacity = self.capacity * self.effective("capacity")
        demand_target = min(self.capacity, effective_capacity)
        remaining = max(0.0, demand_target)
        purchased_value = 0.0

        for source in sorted(active_upstream, key=lambda a: a.unit_price):
            admitted = min(max(0.0, source.quantity_available), remaining)
            source.quantity_available = admitted
            if isinstance(source, Transport):
                source_effective_capacity = (
                    source.capacity * source.effective("capacity")
                )
                source.utilisation = (
                    source.quantity_available / source_effective_capacity
                    if source_effective_capacity > 0.0 else 0.0
                )
            purchased_value += source.unit_price * admitted
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

