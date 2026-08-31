"""
Simulation orchestrator

The Model is the top-level Melodie object.
Melodie calls three methods in fixed order:

    1. create(): instantiate all Melodie objects
    2. setup(): additional initialisation logic after creation
    3. run(): the simulation loop

Step order each timestep:
    1.  Farmer[sa]           produce soja (drought applied)
    2.  Trader[wholesaler]   aggregate and price
    3.  Transport[sa_santos]   move BRA + USA santos_share through Santos
    3.  Transport[sa_paranagua] move BRA + USA (1-santos_share) through Paranagua
    4a. Transport[sea_santos]   ship Santos output -> EU port (Rotterdam)
    4b. Transport[sea_paranagua] ship Paranagua output -> EU port (Hamburg)
    4c. Transport[sea_arg]       ship ARG direct -> EU port (Rotterdam, bypassing SA ports)
    4d. Transport[sea_usa]       ship USA Gulf-> Rotterdam, bypassing SA ports
    5a. Transport[eu_rtm]        Rotterdam: sea_santos + sea_arg + sea_usa -> processors
    5b. Transport[eu_ham]        Hamburg: sea_paranagua -> processors
    6. Process[processor]   crush soja -> meal
    7. Process[feed_manufacturer]   produce compound meal
    8. Trader[feed_trader]  distribute feed
    9. Farmer[eu]           bid and receive feed
    10. Environment         aggregate global state and update prices
    11. DataCollector       record snapshot
"""
import fontTools.misc.arrayTools
import logging
from Melodie import Model
from pathlib import Path
from .event_tracker import EventTracker
from .topology import build_roster
from .environment import SupplyChainEnvironment
from .data_collector import SupplyChainDataCollector

logger = logging.getLogger(__name__)


class SupplyChainModel(Model):

    def create(self):
        """
        Instantiate the env, data collector, and one AgentList per roster archetype.
        Replaces the old hardcoded create_agent_list calls.
        """
        self.environment = self.create_environment(SupplyChainEnvironment)
        self.data_collector = self.create_data_collector(SupplyChainDataCollector)

        # PDL-driven roster: one AgentList per archetype, bound to its model
        # attribute name (self.brazil_farms, ...) so the rest of the model still
        # references lists by name. Replaces the old 16 hardcoded calls.
        self._roster = build_roster(self._roster_pdl_path())
        for entry in self._roster:
            arc = entry.archetype
            setattr(self, arc.name, self.create_agent_list(arc.agent_class))


    def _roster_pdl_path(self) -> str:
        """
        PDL the roster is derived from: the class _pdl_path set by main.py for a
        swapped PDL, else the shipped scenario so the model runs standalone.
        """
        default = Path(__file__).parent / "scenarios" / "s1-soja.pdl.yaml"
        return getattr(self.__class__, "_pdl_path", str(default))


    def setup(self):
        """
        Populate every AgentList in the derived roster, assign roles, and apply
        each archetype's declared params — bindings, literal attrs, and
        scenario-sourced attrs — so agents carry no role-specific init.
        """
        for entry in self._roster:
            arc = entry.archetype
            agent_list = getattr(self, arc.name)
            agent_list.setup_agents(getattr(self.scenario, arc.count_attr))
            # entity-driven capacity binding: an agent reads its own entity's supply shock.
            capacity_key = (entry.entity_ids[0], "supply") if len(entry.entity_ids) == 1 else None
            origin = entry.entity_ids[0] if len(entry.entity_ids) == 1 else ""
            bindings = arc.params.get("bindings", {})
            attrs = arc.params.get("attrs", {})
            scenario_attrs = arc.params.get("scenario_attrs", {})
            for agent in agent_list.agents:
                agent.role = arc.role
                agent.origin = origin
                agent.binding = dict(bindings)   # per-agent copy of the declared slots
                for attr, value in attrs.items():
                    setattr(agent, attr, value)
                for attr, scenario_attr in scenario_attrs.items():
                    setattr(agent, attr, getattr(self.scenario, scenario_attr))
                agent.post_setup()
                if capacity_key is not None:
                    agent.binding = {**agent.binding, "capacity": capacity_key}

        self._prev_shock_scales: dict[tuple[str, str], float] = {}
        self._prev_active_events: set[str] = set()
        self._heartbeat_interval: int = 30

        # Flow wiring and step order, both derived from the PDL graph. A new
        # producer region in a swapped PDL wires in here with no code change.
        from .topology import build_flow_adjacency, execution_order
        self._flow_adjacency = build_flow_adjacency(self._roster_pdl_path())
        self._execution_order: list[str] = execution_order(self._flow_adjacency)


    def upstream_parts(self, name: str) -> list:
        """Active upstream lists feeding `name`, one per source, in flow order.
        Kept ungrouped for callers that need per-source totals."""
        return [getattr(self, src).filter(lambda a: a.active)
                for src in self._flow_adjacency.get(name, ())]

    def upstream(self, name: str):
        """Active upstream agents feeding `name`, concatenated in flow order.
        None if `name` is a source node (e.g. a producer)."""
        combined = None
        for part in self.upstream_parts(name):
            combined = part if combined is None else combined + part
        return combined


    def _collect_snapshot(self) -> dict:
        """
        Headline prices/volumes for console logging, derived from the run's flow
        graph: producers are the source lists, ports the lists feeding a sea crossing.
        """
        from .topology import producer_lists, export_port_lists

        role_of = {e.archetype.name: e.archetype.role for e in self._roster}
        producers = producer_lists(self._flow_adjacency)

        def vw_price(name: str) -> float:
            active = getattr(self, name).filter(lambda a: a.active)
            vol = sum(a.quantity_available for a in active)
            return (sum(a.unit_price * a.quantity_available for a in active) / vol) if vol > 0 else 0.0

        def volume(name: str) -> float:
            return sum(a.quantity_available for a in getattr(self, name).filter(lambda a: a.active))

        # label by role when unique among producers, else by list name.
        role_n = {r: sum(1 for n in producers if role_of.get(n, n) == r)
                  for r in {role_of.get(n, n) for n in producers}}

        def plabel(name: str) -> str:
            role = role_of.get(name, name)
            return (role if role_n[role] == 1 else name).upper()

        return {
            "producers": {plabel(n): vw_price(n) for n in producers},
            "ports": {role_of.get(n, n).upper(): volume(n) for n in export_port_lists(self._flow_adjacency)},
            "soja_px": self.environment.soja_price,
            "feed_px": self.environment.feed_price,
            "supply": self.environment.total_soja_supply,
            "n_active_shocks": sum(1 for v in self.environment.shock_scales.values() if v > 0),
        }


    def _log_event(self, t: int, direction: str, key: tuple[str, str], snap: dict):
        """
        Emit one line per shock state transition.
        """
        entity, field = key
        label = f"{entity}/{field}"
        value = self.environment.get_effective_value(entity, field)
        if direction == "ON":
            pct = (value - 1.0) * 100
            sign = "+" if pct > 0 else ""
            logger.debug(" ▸ DAY %03d ON %-28s %.2f (%s%.0f%%)", t, label, value, sign, pct)
        else:
            logger.debug(" ▸ DAY %03d OFF %-28s → 1.00", t, label)


    def _log_hearbeat(self, t: int, snap: dict):
        """
        Periodic state summary.
        """
        prod = " ".join(f"{k}={v:.0f}" for k, v in snap["producers"].items())
        logger.debug(
            " ... day %03d   shocks=%d  %s soja=%.0f feed=%.0f supply=%.0ft",
            t, snap['n_active_shocks'], prod, snap['soja_px'], snap['feed_px'], snap['supply'],
        )


    def _log_scenario_summary(self, id_scenario: int, total_days: int):
        """
        End-of-scenario summary.
        """
        snap = self._collect_snapshot()
        n_shocks = snap["n_active_shocks"]
        prod = "  ".join(f"{k}={v:.0f}" for k, v in snap["producers"].items())
        ports = "  ".join(f"{k}={v:.0f}t" for k, v in snap["ports"].items())
        prices_line = f"  Final prices: {prod}  soja={snap['soja_px']:.0f}  feed={snap['feed_px']:.0f}"
        supply_line = f"  Final supply: {snap['supply']:.0f}t  {ports}"
        logger.info(
            "Scenario %s complete\n"
            "  ┌─ Scenario %s complete ─%s┐\n"
            "  │  Days: %d  |  Active shocks remaining: %-21s│\n"
            "  │%-63s│\n"
            "  │%-63s│\n"
            "  └%s┘",
            id_scenario, id_scenario, '─' * 50,
            total_days, n_shocks,
            prices_line, supply_line,
            '─' * 63,
        )

    def _do_step(self, t: int) -> None:
        """
        Execute one simulation step at period t. Shared by run() and run_stepwise().
        """
        self.environment.update_shock_scales(t)

        # tracker event logging
        tracker = self.environment._tracker
        if tracker is not None:
            current_events = tracker.get_active_event_ids()
            activated = current_events - self._prev_active_events
            expired = self._prev_active_events - current_events

            for eid in sorted(activated):
                edef = tracker._events.get(eid)
                reason = f"condition: {edef.condition}" if edef and edef.condition else "unconditional"
                if edef and edef.impacts:
                    impact_str = " -> " + ", ".join(
                        f"{edef.entity}/{f}={v:.2f}" for f, v in edef.impacts.items()
                    )
                else:
                    impact_str = ""
                dur_str = f", expires day {t + edef.duration}" if edef and edef.duration > 0 else ", permanent"
                logger.debug(" © DAY %03d EVENT ON %-35s (%s%s%s)", t, eid, reason, impact_str, dur_str)
            for eid in sorted(expired):
                logger.debug(" ® DAY %03d EVENT OFF %-35s (duration elapsed)", t, eid)

            self._prev_active_events = current_events

        # Step each list after its upstream sources, in the order derived from
        # the wiring graph (topology.execution_order, cached in setup).
        for name in self._execution_order:
            getattr(self, name).method_foreach('step', ())

        # Global state update
        self.environment.step()

        # --- Event-based logging ---
        snap = self._collect_snapshot()
        current_scales = dict(self.environment.shock_scales)

        # detect shock state transitions
        for key, scale in current_scales.items():
            prev = self._prev_shock_scales.get(key, 0.0)
            if prev == 0.0 and scale > 0.0:
                self._log_event(t, "ON", key, snap)
            elif prev > 0.0 and scale == 0.0:
                self._log_event(t, "OFF", key, snap)

        self._prev_shock_scales = current_scales

        # heartbeat every N days + always on day 0
        if t == 0 or t % self._heartbeat_interval == 0:
            self._log_hearbeat(t, snap)

        # Record snapshot
        self.data_collector.collect(t)


    def _init_event_tracker(self) -> None:
        """
        Attach the EventTracker for PDL runs. No-op in static / non-PDL mode.
        Shard by run() and run_stepwise().
        """
        if getattr(self.scenario, "id", 0) == 0:
            return  # baseline: no conditional events (no-shock)
        registry = getattr(self.__class__, "_event_registry", None)
        if registry is not None:
            self.environment._tracker = EventTracker(
                events=registry["events"],
                timeline=registry["timeline"],
            )

    def _all_agent_lists(self) -> list:
        """Every AgentList in the model, from the PDL-derived roster. Order is
        irrelevant; callers aggregate into sets/dicts."""
        return [getattr(self, entry.archetype.name) for entry in self._roster]

    def _crosscheck_bindings(self) -> None:
        """
        Warn (don't fail) when an agent is bound to a PDL (entity, field) the loaded
        scenario never shocks, so those agents run unshocked; surfaces region-swap typos.
        """
        tracker = self.environment._tracker
        if tracker is None:
            return  # baseline / non-PDL run: nothing to cross-check
        known = tracker.known_keys()

        bound: dict[tuple[str, str], set[str]] = {}
        for agent_list in self._all_agent_lists():
            for agent in agent_list.agents:
                for key in agent.binding.values():
                    bound.setdefault(key, set()).add(agent.role)

        for key, roles in sorted(bound.items()):
            if key not in known:
                entity, field = key
                roles_str = ", ".join(sorted(roles))
                logger.warning("binding %s/%s not shocked by loaded PDL - roles [%s] run unshocked", entity, field, roles_str)

    def run(self):
        """
        Main simulation loop, called by Melodie after create() and setup(): init
        tracker, cross-check bindings, step each period, then summarise and save.
        """
        self._init_event_tracker()
        self._crosscheck_bindings()
        for t in self.iterator(self.scenario.period_num):
            self._do_step(t)
        self._log_scenario_summary(self.scenario.id, self.scenario.period_num)
        self.data_collector.save()

    def run_stepwise(self):
            """
            Generator variant for external step-by-step control (e.g. RL agents).
            Yields a state snapshot dict after every step; the caller drives the loop.
            """
            from .db_config import PostgresDBConfig
            from .tick_writer import TickWriter

            id_scenario = getattr(self.scenario, "id", 0)
            tick_writer = TickWriter.from_config(PostgresDBConfig(), reset=(id_scenario == 0))

            self._init_event_tracker()
            self._crosscheck_bindings()

            for t in range(self.scenario.period_num):
                self._do_step(t)
                tick_writer.write_tick(self, id_scenario=id_scenario, id_run=0, t=t)
                yield {
                    "step": t,
                    "shock_scale": self.environment.shock_scale,
                    "soja_price": self.environment.soja_price,
                    "feed_price": self.environment.feed_price,
                    "total_soja_supply": self.environment.total_soja_supply,
                    "transport_utilisation": self.environment.transport_utilisation,
                }
