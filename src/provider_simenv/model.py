"""
Simulation orchestrator

The Model is the top-level Melodie object.
Melodie calls three methods in fixed order:

    1. create(): instantiate all Melodie objects
    2. setup(): additional initialisation logic after creation
    3. run(): the simulation loop

Step order each timestep:
    1. Farmer[sa]           produce soja (drought applied)
    2. Trader[wholesaler]   aggregate and price
    3. Transport[sa_land]   moves good to SA export port
    4. Transport[sea]       move goods to EU port
    5. Transport[eu_land]   move goods to processors
    6. Process[processor]   crush soja -> meal
    7. Process[feed_manufacturer]   produce compound meal
    8. Trader[feed_trader]  distribute feed
    9. Farmer[eu]           bid and receive feed
    10. Environment         aggregate global state and update prices
    11. DataCollector       record snapshot
"""
import fontTools.misc.arrayTools
from Melodie import Model
from agents import (
    Farmer, Trader, Transport, Process,
    ROLE_BRA, ROLE_USA, ROLE_EU,
    ROLE_WHOLESALER, ROLE_FEED_TRADER,
    ROLE_SA_LAND, ROLE_SEA, ROLE_EU_LAND,
    ROLE_PROCESSOR, ROLE_FEED_MANUFACTURER,
)
from environment import SupplyChainEnvironment
from data_collector import SupplyChainDataCollector


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

        self.bra_farmers = self.create_agent_list(Farmer)
        self.usa_farmers = self.create_agent_list(Farmer)
        self.eu_farmers = self.create_agent_list(Farmer)

        self.wholesalers = self.create_agent_list(Trader)
        self.feed_traders = self.create_agent_list(Trader)

        self.transport_sa = self.create_agent_list(Transport)
        self.sea_transport = self.create_agent_list(Transport)
        self.transport_eu = self.create_agent_list(Transport)

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
        self._setup_with_role(self.usa_farmers, self.scenario.n_usa_farmers, ROLE_USA)
        self._setup_with_role(self.eu_farmers, self.scenario.n_eu_farmers, ROLE_EU)
        self._setup_with_role(self.wholesalers, self.scenario.n_wholesalers, ROLE_WHOLESALER)
        self._setup_with_role(self.feed_traders, self.scenario.n_feed_traders, ROLE_FEED_TRADER)
        self._setup_with_role(self.transport_sa, self.scenario.n_transport_sa, ROLE_SA_LAND)
        self._setup_with_role(self.sea_transport, self.scenario.n_transport_sea, ROLE_SEA)
        self._setup_with_role(self.transport_eu, self.scenario.n_transport_eu, ROLE_EU_LAND)
        self._setup_with_role(self.processors, self.scenario.n_processors, ROLE_PROCESSOR)
        self._setup_with_role(self.feed_manufacturers, self.scenario.n_feed_manufacturers, ROLE_FEED_MANUFACTURER)

    def _do_step(self, t: int) -> None:
        """
        Execute one simulation step at period t. Shared by run() and run_stepwise().
        """
        self.environment.update_shock_scale(t)

        # Production
        self.bra_farmers.method_foreach('step', ())
        self.usa_farmers.method_foreach('step', ())
        self.wholesalers.method_foreach('step', ())

        # Transport
        self.transport_sa.method_foreach('step', ())
        self.sea_transport.method_foreach('step', ())
        self.transport_eu.method_foreach('step', ())

        # Processing & distribution
        self.processors.method_foreach('step', ())
        self.feed_manufacturers.method_foreach('step', ())
        self.feed_traders.method_foreach('step', ())

        # End consumption
        self.eu_farmers.method_foreach('step', ())

        # Global state update
        self.environment.step()

        # Terminal output
        n_bra_active = sum(1 for a in self.bra_farmers.agents if a.active)
        n_usa_active = sum(1 for a in self.usa_farmers.agents if a.active)
        n_eu_active = sum(1 for a in self.eu_farmers.agents if a.active)

        # BRA / USA spot prices
        active_bra = self.bra_farmers.filter(lambda f: f.active)
        active_usa = self.usa_farmers.filter(lambda f: f.active)
        bra_vol = sum(f.quantity_available for f in active_bra)
        usa_vol = sum(f.quantity_available for f in active_usa)
        bra_px = (
            sum(f.unit_price * f.quantity_available for f in active_bra) / bra_vol
            if bra_vol > 0 else 0.0
        )
        usa_px = (
            sum(f.unit_price * f.quantity_available for f in active_usa) / usa_vol
            if usa_vol > 0 else 0.0
        )

        # wholesaler sourcing totals across all active wholesalers
        active_w = self.wholesalers.filter(lambda w: w.active)
        w_bra_total = sum(w.bra_volume for w in active_w)
        w_usa_total = sum(w.usa_volume for w in active_w)
        cheaper = "BRA" if bra_px <= usa_px else "USA"

        print(
            f"[s{self.scenario.id} t{t:03d}] "
            f"shock={self.environment.shock_scale:.2f} | "
            f"px: BRA={bra_px:6.1f} USA={usa_px:6.1f} EUR/t [{cheaper}] | "
            f"soja={self.environment.soja_price:7.1f} feed={self.environment.feed_price:7.1f} EUR/t | "
            f"W<-BRA={w_bra_total:6.1f}t USA={w_usa_total:6.1f}t | "
            f"farms BRA={n_bra_active} USA={n_usa_active} EU={n_eu_active}"
        )

        # Record snapshot
        self.data_collector.collect(t)

    def run(self):
        """
        Main simulation loop. Melodie calls this after create() and setup().

        self.iterator(n): yields period 0..n-1, handles any visualiser updates per step
        agent_list.method_foreach(method_name, args): calls method_name on every agent in the list; args must be a tuple.
        """

        for t in self.iterator(self.scenario.period_num):
            self._do_step(t)
        self.data_collector.save()

    def run_stepwise(self):
            """
            Generator variant for external step-by-step control (e.g. RL agents)

            Yields a state snapshot dict after every step. The caller drives the loop:

                for state in model.run_stepwise():
                    print(state['soja_price'])
                    # TODO: RL actions here
            """
            from db_config import PostgresDBConfig
            from tick_writer import TickWriter

            id_scenario = getattr(self.scenario, "id", 0)
            tick_writer = TickWriter.from_config(PostgresDBConfig(), reset=(id_scenario == 0))

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
