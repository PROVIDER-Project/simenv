"""
Simulation output collection.

Melodie' DataCollector records agent and environment state at each step,
writing results to a structured output (CSV)
"""

from Melodie import DataCollector

class SupplyChainDataCollector(DataCollector):
    """
    collects state snapshots every simulation step

    agent properties: lit of attribute names to record for each agent type
    environment properties: lit of attribute names to record for each environment type
    """

    def setup(self):
        # Agent-level variables to record each step
        self.add_agent_property("sa_farmers", "quantity_available")
        self.add_agent_property("sa_farmers", "unit_price")
        self.add_agent_property("sa_farmers", "active")

        self.add_agent_property("wholesalers", "quantity_available")
        self.add_agent_property("wholesalers", "unit_price")

        self.add_agent_property("processors", "quantity_available")
        self.add_agent_property("processors", "unit_price")

        self.add_agent_property("feed_manufacturers", "quantity_available")
        self.add_agent_property("feed_manufacturers", "unit_price")

        self.add_agent_property("feed_traders", "quantity_available")
        self.add_agent_property("feed_traders", "unit_price")

        self.add_agent_property("eu_farmers", "feed_received")
        self.add_agent_property("eu_farmers", "livestock_output")
        self.add_agent_property("eu_farmers", "active")


        # Environment-level variables to record each step
        self.add_environment_property("soja_price")
        self.add_environment_property("feed_price")
        self.add_environment_property("shock_scale")
        self.add_environment_property("drought_severity")
        self.add_environment_property("total_soja_supply")
        self.add_environment_property("transport_utilisation")
        self.add_environment_property("current_step")

