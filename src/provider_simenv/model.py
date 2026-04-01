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

from Melodie import Model
from agents import (
    Farmer, Trader, Transport, Process,
    ROLE_SA, ROLE_EU,
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

        self.sa_farmers = self.create_agent_list(Farmer)
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
        self._setup_with_role(self.sa_farmers, self.scenario.n_sa_farmers, ROLE_SA)
        self._setup_with_role(self.eu_farmers, self.scenario.n_eu_farmers, ROLE_EU)
        self._setup_with_role(self.wholesalers, self.scenario.n_wholesalers, ROLE_WHOLESALER)
        self._setup_with_role(self.feed_traders, self.scenario.n_feed_traders, ROLE_FEED_TRADER)
        self._setup_with_role(self.transport_sa, self.scenario.n_transport_sa, ROLE_SA_LAND)
        self._setup_with_role(self.sea_transport, self.scenario.n_transport_sea, ROLE_SEA)
        self._setup_with_role(self.transport_eu, self.scenario.n_transport_eu, ROLE_EU_LAND)
        self._setup_with_role(self.processors, self.scenario.n_processors, ROLE_PROCESSOR)
        self._setup_with_role(self.feed_manufacturers, self.scenario.n_feed_manufacturers, ROLE_FEED_MANUFACTURER)


    def run(self):
        """
        Main simulation loop. Melodie calls this after create() and setup().

        self.iterator(n): yields period 0..n-1, handles any visualiser updates per step
        agent_list.method_foreach(method_name, args): calls method_name on every agent in the list; args must be a tuple.
        """

        for t in self.iterator(self.scenario.period_num):
            self.environment.update_shock_scale(t)
            # Production
            self.sa_farmers.method_foreach('step', ())
            self.wholesalers.method_foreach('step', ())

            # Transport
            self.transport_sa.method_foreach('step', ())
            self.sea_transport.method_foreach('step', ())
            self.transport_eu.method_foreach('step', ())

            # Processing and distribution
            self.processors.method_foreach('step', ())
            self.feed_manufacturers.method_foreach('step', ())
            self.feed_traders.method_foreach('step', ())

            # end consumption
            self.eu_farmers.method_foreach('step', ())

            # global state update
            self.environment.step()

            # record snapshot
            self.data_collector.collect(t)

        self.data_collector.save()