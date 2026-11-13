"""
Simulation output collection.

Melodie' DataCollector records agent and environment state at each step,
writing results to a structured output (CSV)
"""

from collections.abc import Callable
from typing import cast

from Melodie import DataCollector
from MelodieInfra import Table, TableRow, objs_to_table_row_vectorizer

from .agents import (
    ROLE_CONSUMER,
    ROLE_FEED_MANUFACTURER,
    ROLE_FEED_TRADER,
    ROLE_LAND_TRANSPORT,
    ROLE_PROCESSOR,
    ROLE_PRODUCER,
    ROLE_SEA_TRANSPORT,
    ROLE_WHOLESALER,
)

TRANSPORT_PROPS = (
    "quantity_available", "unit_price", "utilisation", "capacity", "active",
    "effective_capacity",
)

_PROPS_BY_ROLE = {
    ROLE_PRODUCER: ("quantity_available", "unit_price", "active"),
    ROLE_CONSUMER: ("feed_received", "livestock_output", "active"),
    ROLE_WHOLESALER: (
        "quantity_available", "unit_price", "storage_utilization",
    ),
    ROLE_PROCESSOR: (
        "quantity_available", "unit_price", "input_received",
        "input_processed", "unused_input",
    ),
    ROLE_FEED_MANUFACTURER: (
        "quantity_available", "unit_price", "input_received",
        "input_processed", "unused_input",
    ),
    ROLE_FEED_TRADER: ("quantity_available", "unit_price"),
    ROLE_LAND_TRANSPORT: TRANSPORT_PROPS,
    ROLE_SEA_TRANSPORT: TRANSPORT_PROPS,
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

    def append_agent_properties_by_records(
        self, container_name, prop_names, container, period,
    ):
        """Let Melodie collect read-only properties as well as stored fields.

        Its default schema initialization reads __dict__, excluding adapter
        properties. Row collection already uses attribute access; only the
        first table initialization needs adapting.
        """
        if container_name not in self.agent_properties_dict and len(container):
            agent = container.agents[0]
            props = {"id_scenario": 0, "id_run": 0, "period": 0, "id": 0}
            props.update({name: getattr(agent, name) for name in prop_names})
            row_cls = TableRow.subcls_from_dict(props)
            self.agent_properties_dict[container_name] = Table(
                row_cls, self._CORE_PROPERTIES_ + ["id"] + prop_names,
            )
            # Melodie types these callbacks as unary, but invokes them with
            # (table, agent). Keep that framework typing mismatch local.
            collectors = cast(
                dict[str, Callable[[Table, object], object]],
                self._agent_properties_collectors,
            )
            collectors[container_name] = (
                objs_to_table_row_vectorizer(row_cls, prop_names)
            )
        super().append_agent_properties_by_records(
            container_name, prop_names, container, period,
        )
