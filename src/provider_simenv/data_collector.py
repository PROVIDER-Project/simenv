"""
Simulation output collection.

Melodie' DataCollector records agent and environment state at each step,
writing results to a structured output (CSV)
"""

from Melodie import DataCollector

from .agents import (
    ROLE_CONSUMER,
    ROLE_FEED_MANUFACTURER,
    ROLE_FEED_TRADER,
    ROLE_PROCESSOR,
    ROLE_PRODUCER,
    ROLE_WHOLESALER,
)

# Roles omitted here (ports, sea transports) are not recorded.
_PROPS_BY_ROLE = {
    ROLE_PRODUCER: ("quantity_available", "unit_price", "active"),
    ROLE_CONSUMER: ("feed_received", "livestock_output", "active"),
    ROLE_WHOLESALER: (
        "quantity_available", "unit_price", "storage_utilization",
    ),
    ROLE_PROCESSOR: ("quantity_available", "unit_price"),
    ROLE_FEED_MANUFACTURER: ("quantity_available", "unit_price"),
    ROLE_FEED_TRADER: ("quantity_available", "unit_price"),
}

# Environment-level variables to record each step
ENVIRONMENT_PROPS = (
    "soy_price", "feed_price", "shock_scale", "drought_severity",
    "total_soy_supply", "transport_utilisation", "current_step",
)


def result_table_name(list_name: str) -> str:
    """
    Melodie's output name for a recorded agent list:
    ``brazil_farms`` -> ``Result_Simulator_BrazilFarms``.
    Single-sourced here so the CSV files and the export bundle
    agree on one name per list.
    """
    return "Result_Simulator_" + "".join(p.title() for p in list_name.split("_"))


class SupplyChainDataCollector(DataCollector):
    """
    collects state snapshots every simulation step

    agent properties: lit of attribute names to record for each agent type
    environment properties: lit of attribute names to record for each environment type
    """

    @property
    def status(self) -> bool:
        # Melodie default check broken in normal Simulator.run() path
        return True

    def setup(self):
        for entry in self.model._roster:
            props = _PROPS_BY_ROLE.get(entry.archetype.role)
            if props is None:
                continue
            for prop in props:
                self.add_agent_property(entry.archetype.name, prop)

        for prop in ENVIRONMENT_PROPS:
            self.add_environment_property(prop)
