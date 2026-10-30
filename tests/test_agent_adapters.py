"""Framework-boundary contracts and cross-agent state synchronization."""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from jsonschema import ValidationError

from provider_simenv.agents import Farmer, Process, Trader, Transport
from provider_simenv.model import SupplyChainModel
from provider_simenv.scenario import SupplyChainScenario


def model_with_agents():
    model = SupplyChainModel(cast(Any, SimpleNamespace()), SupplyChainScenario(1))
    model._setup()
    return model


def test_adapter_uses_validated_public_contract():
    model = model_with_agents()
    farmer = model.brazil_farms.agents[0]
    farmer.active = "invalid boolean"
    with pytest.raises(ValidationError):
        farmer.step()


def test_late_capacity_binding_and_external_parameter_changes():
    model = model_with_agents()
    farmer = model.brazil_farms.agents[0]
    farmer.binding = {"capacity": ("test_entity", "supply")}
    model.environment.get_effective_value = lambda *key: 0.25
    farmer.base_yield = 200.0
    farmer.step(drought_severity=0.9)
    assert farmer.quantity_available == 50.0
    assert "quantity_available" in farmer.__dict__


def test_upstream_mutation_survives_next_inactive_step():
    model = model_with_agents()
    imports = model.rotterdam_port.agents[0]
    imports.capacity = 100.0
    # Advance once to populate the full chain, including import admission.
    for name in model._execution_order:
        getattr(model, name).method_foreach("step", ())
    sources = list(model.upstream(imports.list_name))
    assert sum(source.quantity_available for source in sources) == 100.0
    for source in sources:
        quantity, utilisation = source.quantity_available, source.utilisation
        source.active = False
        source.step()
        assert (source.quantity_available, source.utilisation) == (quantity, utilisation)


def test_defaults_are_published_before_model_parameter_assignment():
    farmer = Farmer(3)
    farmer.setup()
    assert farmer.__dict__["base_yield"] == 0.0
    assert farmer.__dict__["size_factor"] == 1.0
    assert farmer.__dict__["active"] is True


def test_unknown_source_patch_is_not_dropped():
    agent = Transport(1)
    agent.setup()
    with pytest.raises(KeyError):
        agent._apply_result({"upstream_updates": [
            {"key": "missing", "quantity_available": 1.0},
        ]}, {})


@pytest.mark.parametrize("cls", [Farmer, Trader, Process, Transport])
def test_inactive_adapter_does_not_require_framework_observations(cls):
    agent = cls(1)
    agent.setup()
    agent.active = False
    agent.step()
    assert agent.active is False


@pytest.mark.parametrize("cls,raises", [
    (Farmer, True), (Trader, False), (Process, False), (Transport, True),
])
def test_unknown_role_dispatch_precedes_framework_observations(cls, raises):
    agent = cls(1)
    agent.setup()
    agent.role = "unknown"
    if raises:
        with pytest.raises(ValueError, match="unknown role"):
            agent.step()
    else:
        agent.step()
