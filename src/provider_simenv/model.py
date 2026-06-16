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
from Melodie import Model
from .event_tracker import EventTracker
from .agents import (
    Farmer, Trader, Transport, Process,
    ROLE_BRA, ROLE_ARG, ROLE_USA, ROLE_EU,
    ROLE_WHOLESALER, ROLE_FEED_TRADER,
    ROLE_SA_SANTOS, ROLE_SA_PARANAGUA,
    ROLE_SEA_SANTOS, ROLE_SEA_PARANAGUA, ROLE_SEA_ARG, ROLE_SEA_USA,
    ROLE_EU_RTM, ROLE_EU_HAM,
    ROLE_PROCESSOR, ROLE_FEED_MANUFACTURER,
)
from .environment import SupplyChainEnvironment
from .data_collector import SupplyChainDataCollector


class SupplyChainModel(Model):

    def create(self):
        """
        Instantiate all Melodie components.

        create_environment(cls): create our env object
        create_data_collector(cls): create our data collector object
        create_agent_list(cls): create an AgentList for one type
        .setup_agents(n): populates it with n agents and calls setup() on each one
        """
        self.environment = self.create_environment(SupplyChainEnvironment)
        self.data_collector = self.create_data_collector(SupplyChainDataCollector)

        # Farmer lists
        self.bra_farmers = self.create_agent_list(Farmer)
        self.arg_farmers = self.create_agent_list(Farmer)
        self.usa_farmers = self.create_agent_list(Farmer)
        self.eu_farmers = self.create_agent_list(Farmer)

        # Trader lists
        self.wholesalers = self.create_agent_list(Trader)
        self.feed_traders = self.create_agent_list(Trader)

        # SA land transport (two ports)
        self.transport_sa_santos = self.create_agent_list(Transport)
        self.transport_sa_paranagua = self.create_agent_list(Transport)

        # sea lanes: Santos -> Rotterdam, Paranagua -> Hamburg, ARG direct -> Rotterdam
        self.sea_lane_santos = self.create_agent_list(Transport)
        self.sea_lane_paranagua = self.create_agent_list(Transport)
        self.sea_lane_arg = self.create_agent_list(Transport)
        self.sea_lane_usa = self.create_agent_list(Transport)

        # EU entry points (Rotterdam: STO+ARG+USA, Hamburg: PRG only)
        self.transport_eu_rtm = self.create_agent_list(Transport)
        self.transport_eu_ham = self.create_agent_list(Transport)

        self.processors = self.create_agent_list(Process)
        self.feed_manufacturers = self.create_agent_list(Process)


    def _setup_with_role(self, agent_list, n, role):
        """
        Helper: create n agents, assign role, thn run role-specific init.
        """
        agent_list.setup_agents(n)
        for agent in agent_list.agents:
            agent.role = role
            agent.post_setup()


    def setup(self):
        """
        Populate all AgentLists and assign roles.

        Uses _setup_with_role() so the pattern is written once, not repeated nine times.
        """
        self._setup_with_role(self.bra_farmers, self.scenario.n_bra_farmers, ROLE_BRA)
        self._setup_with_role(self.arg_farmers, self.scenario.n_arg_farmers, ROLE_ARG)
        self._setup_with_role(self.usa_farmers, self.scenario.n_usa_farmers, ROLE_USA)
        self._setup_with_role(self.eu_farmers, self.scenario.n_eu_farmers, ROLE_EU)

        self._setup_with_role(self.wholesalers, self.scenario.n_wholesalers, ROLE_WHOLESALER)
        self._setup_with_role(self.feed_traders, self.scenario.n_feed_traders, ROLE_FEED_TRADER)

        self._setup_with_role(self.transport_sa_santos, self.scenario.n_transport_sa_santos, ROLE_SA_SANTOS)
        self._setup_with_role(self.transport_sa_paranagua, self.scenario.n_transport_sa_paranagua, ROLE_SA_PARANAGUA)

        self._setup_with_role(self.sea_lane_santos, self.scenario.n_sea_lane_santos, ROLE_SEA_SANTOS)
        self._setup_with_role(self.sea_lane_paranagua, self.scenario.n_sea_lane_paranagua, ROLE_SEA_PARANAGUA)
        self._setup_with_role(self.sea_lane_arg, self.scenario.n_sea_lane_arg, ROLE_SEA_ARG)
        self._setup_with_role(self.sea_lane_usa, self.scenario.n_sea_lane_usa, ROLE_SEA_USA)

        self._setup_with_role(self.transport_eu_rtm, self.scenario.n_transport_eu_rtm, ROLE_EU_RTM)
        self._setup_with_role(self.transport_eu_ham, self.scenario.n_transport_eu_ham, ROLE_EU_HAM)

        self._setup_with_role(self.processors, self.scenario.n_processors, ROLE_PROCESSOR)
        self._setup_with_role(self.feed_manufacturers, self.scenario.n_feed_manufacturers, ROLE_FEED_MANUFACTURER)

        self._prev_shock_scales: dict[tuple[str, str], float] = {}
        self._prev_active_events: set[str] = set()
        self._heartbeat_interval: int = 30


    def _collect_snapshot(self) -> dict:
        """
        Gather current prices and volumes for logging
        """
        active_bra = self.bra_farmers.filter(lambda f: f.active)
        active_arg = self.arg_farmers.filter(lambda f: f.active)
        active_usa = self.usa_farmers.filter(lambda f: f.active)
        bra_vol = sum(f.quantity_available for f in active_bra)
        arg_vol = sum(f.quantity_available for f in active_arg)
        usa_vol = sum(f.quantity_available for f in active_usa)
        return {
            "bra_px": (sum(f.unit_price * f.quantity_available for f in active_bra) / bra_vol) if bra_vol > 0 else 0.0,
            "arg_px": (sum(f.unit_price * f.quantity_available for f in active_arg) / arg_vol) if arg_vol > 0 else 0.0,
            "usa_px": (sum(f.unit_price * f.quantity_available for f in active_usa) / usa_vol) if usa_vol > 0 else 0.0,
            "soja_px": self.environment.soja_price,
            "feed_px": self.environment.feed_price,
            "supply": self.environment.total_soja_supply,
            "sto_vol": sum(a.quantity_available for a in self.transport_sa_santos.filter(lambda a: a.active)),
            "prg_vol": sum(a.quantity_available for a in self.transport_sa_paranagua.filter(lambda a: a.active)),
            "n_active_shocks": sum(1 for v in self.environment.shock_scales.values() if v > 0),
        }


    def _log_event(self, t: int, direction: str, key: tuple[str, str], snap: dict):
        """
        layer 1: emit one line per shock state transition
        """
        entity, field = key
        label = f"{entity}/{field}"
        value = self.environment.get_effective_value(entity, field)
        if direction == "ON":
            pct = (value - 1.0) * 100
            sign = "+" if pct > 0 else ""
            print(f" ▸ DAY {t:03d} ON {label:<28s} {value:.2f} ({sign}{pct:.0f}%)")
        else:
            print(f" ▸ DAY {t:03d} OFF {label:<28s} → 1.00")


    def _log_hearbeat(self, t: int, snap: dict):
        """
        layer 2: periodic state summary
        """
        print(
            f" ... day {t:03d}   "
            f"shocks={snap['n_active_shocks']}  "
            f"BRA={snap['bra_px']:.0f} ARG={snap['arg_px']:.0f} USA={snap['usa_px']:.0f} "
            f"soja={snap['soja_px']:.0f} feed={snap['feed_px']:.0f} "
            f"supply={snap['supply']:.0f}t"
            )


    def _log_scenario_summary(self, id_scenario: int, total_days: int):
        """
        layer 3: end of scenario summary
        """
        snap = self._collect_snapshot()
        n_shocks = snap["n_active_shocks"]
        print()
        print(f"  ┌─ Scenario {id_scenario} complete ─{'─' * 50}┐")
        print(f"  │  Days: {total_days}  |  Active shocks remaining: {n_shocks:<21}│")
        print(f"  │  Final prices: BRA={snap['bra_px']:.0f}  ARG={snap['arg_px']:.0f}  "
              f"USA={snap['usa_px']:.0f}  soja={snap['soja_px']:.0f}  feed={snap['feed_px']:.0f}{'':>4}│")
        print(f"  │  Final supply: {snap['supply']:.0f}t  "
              f"STO={snap['sto_vol']:.0f}t  PRG={snap['prg_vol']:.0f}t{'':>22}│")
        print(f"  └{'─' * 63}┘")
        print()

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
                print(f" © DAY {t:03d} EVENT ON {eid:<35s} ({reason}{impact_str}{dur_str})")
            for eid in sorted(expired):
                print(f" ® DAY {t:03d} EVENT OFF {eid:<35s} (duration elapsed)")

            self._prev_active_events = current_events

        # Production
        self.bra_farmers.method_foreach('step', ())
        self.arg_farmers.method_foreach('step', ())
        self.usa_farmers.method_foreach('step', ())
        self.wholesalers.method_foreach('step', ())

        # Transport
        self.transport_sa_santos.method_foreach('step', ())
        self.transport_sa_paranagua.method_foreach('step', ())
        self.sea_lane_santos.method_foreach('step', ())
        self.sea_lane_paranagua.method_foreach('step', ())
        self.sea_lane_arg.method_foreach('step', ())
        self.sea_lane_usa.method_foreach('step', ())
        self.transport_eu_rtm.method_foreach('step', ())
        self.transport_eu_ham.method_foreach('step', ())

        # Processing & distribution
        self.processors.method_foreach('step', ())
        self.feed_manufacturers.method_foreach('step', ())
        self.feed_traders.method_foreach('step', ())

        # End consumption
        self.eu_farmers.method_foreach('step', ())

        # Global state update
        self.environment.step()

        # --- Event-based logging ---
        snap = self._collect_snapshot()
        current_scales = dict(self.environment.shock_scales)

        # layer 1: detect transitions
        for key, scale in current_scales.items():
            prev = self._prev_shock_scales.get(key, 0.0)
            if prev == 0.0 and scale > 0.0:
                self._log_event(t, "ON", key, snap)
            elif prev > 0.0 and scale == 0.0:
                self._log_event(t, "OFF", key, snap)

        self._prev_shock_scales = current_scales

        # layer 2: heartbeat every N days + always on day 0
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

    def run(self):
        """
        Main simulation loop. Melodie calls this after create() and setup().

        self.iterator(n): yields period 0..n-1, handles any visualiser updates per step
        agent_list.method_foreach(method_name, args): calls method_name on every agent in the list; args must be a tuple.
        """
        self._init_event_tracker()
        for t in self.iterator(self.scenario.period_num):
            self._do_step(t)
        self._log_scenario_summary(self.scenario.id, self.scenario.period_num)
        self.data_collector.save()

    def run_stepwise(self):
            """
            Generator variant for external step-by-step control (e.g. RL agents)

            Yields a state snapshot dict after every step. The caller drives the loop:

                for state in model.run_stepwise():
                    print(state['soja_price'])
                    # TODO: RL actions here
            """
            from .db_config import PostgresDBConfig
            from .tick_writer import TickWriter

            id_scenario = getattr(self.scenario, "id", 0)
            tick_writer = TickWriter.from_config(PostgresDBConfig(), reset=(id_scenario == 0))

            self._init_event_tracker()

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
