"""Sidecar settings must reach standalone contracts without scenario coupling."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml

from provider_simenv.model import SupplyChainModel
from provider_simenv.scenario import SupplyChainScenario
from provider_simenv.topology import build_roster, sidecar_path

SHIPPED = (Path(__file__).parents[1] / "src/provider_simenv/scenarios"
           / "s1-soja.pdl.yaml")


def configured_pdl(tmp_path, economics):
    # Renaming catches implicit links to specific shipped entity names.
    pdl = tmp_path / "renamed.pdl.yaml"
    pdl.write_text(SHIPPED.read_text().replace("brazil_farms", "orchards"))
    roster = yaml.safe_load(sidecar_path(SHIPPED).read_text())
    roster = yaml.safe_load(yaml.safe_dump(roster).replace(
        "brazil_farms", "orchards",
    ))
    roster["economics"] = economics
    sidecar_path(pdl).write_text(yaml.safe_dump(roster))
    return pdl


def model_for(pdl, monkeypatch):
    monkeypatch.setattr(SupplyChainModel, "_pdl_path", str(pdl), raising=False)
    model = SupplyChainModel(cast(Any, SimpleNamespace()), SupplyChainScenario(1))
    model._setup()
    return model


def test_parameters_and_aliases_override_scenario(tmp_path, monkeypatch):
    pdl = configured_pdl(tmp_path, {"orchards": {
        "parameters": {"fixed_costs": 100., "base_yield": 10.,
                       "input_cost_shares": {"nutrients": .25}},
        "bindings": {"nutrients": ["fertilizer_supply", "price"]},
    }})
    model = model_for(pdl, monkeypatch)
    farm = model.orchards.agents[0]
    model.environment.get_effective_value = (
        lambda entity, field: 2. if field == "price" else 1.
    )
    farm.step()
    assert farm.fixed_costs == 100.
    assert farm.quantity_available == 10.
    assert farm.unit_price == pytest.approx(13.75)
    assert model.us_farms.agents[0].fixed_costs == 48000.


@pytest.mark.parametrize("target", [
    "santos_port", "sea_transport_santos_port__rotterdam_port",
])
def test_transport_margin_survives_multiple_steps(tmp_path, monkeypatch, target):
    pdl = configured_pdl(tmp_path, {target: {
        "parameters": {"margin": .5, "fixed_costs": 100.},
    }})
    model = model_for(pdl, monkeypatch)
    route = getattr(model, target).agents[0]
    assert route.margin_transport == .5
    for _ in range(2):
        for name in model._execution_order:
            getattr(model, name).method_foreach("step", ())
        assert route.margin_transport == .5
    assert model.hamburg_port.agents[0].margin_transport == .1


@pytest.mark.parametrize("economics", [
    [], None, {"missing": {}}, {"orchards": []},
    {"orchards": {"unknown": 1}},
    {"orchards": {"parameters": []}},
    {"orchards": {"parameters": {"active": False}}},
    {"orchards": {"parameters": {"throughput_capacity": 10.}}},
    {"orchards": {"parameters": {"fixed_costs": float("nan")}}},
    {"orchards": {"parameters": {"base_yield": True}}},
    {"orchards": {"parameters": {"input_cost_shares": {"typo": .25}}}},
    {"orchards": {"parameters": {"input_cost_shares": {"capacity": .25}}}},
    {"orchards": {"parameters": {"input_cost_shares": {"x": .25}},
                  "bindings": {"x": ["fertilizer_supply", "supply"]}}},
    {"orchards": {"bindings": {"capacity": ["orchards", "supply"]}}},
    {"orchards": {"bindings": {"x": ["missing", "price"]}}},
    {"orchards": {"bindings": {"x": ["fertilizer_supply", "typo"]}}},
    {"orchards": {"bindings": {"x": "fertilizer_supply"}}},
    {"orchards": {"bindings": []}},
    {"orchards": {"bindings": {"fertilizer": ["fertilizer_supply", "supply"]}}},
    {"santos_port": {"bindings": {"energy": ["gas_supply", "supply"]}}},
    {"eu_oil_mills": {"parameters": {"conversion_ratio": 0.}}},
])
def test_invalid_economics_fails_before_setup(tmp_path, economics):
    pdl = configured_pdl(tmp_path, economics)
    with pytest.raises(ValueError, match="economics"):
        build_roster(pdl)


def test_optional_section_and_explicit_empty_exposure(tmp_path, monkeypatch):
    pdl = configured_pdl(tmp_path, {"orchards": {
        "parameters": {"input_cost_shares": {}, "fixed_costs": 36000.,
                       "base_yield": 100.},
    }})
    model = model_for(pdl, monkeypatch)
    farm = model.orchards.agents[0]
    model.environment.get_effective_value = (
        lambda entity, field: 2. if field == "price" else 1.
    )
    farm.step()
    assert farm.unit_price == pytest.approx(396.)
    doc = yaml.safe_load(sidecar_path(pdl).read_text())
    del doc["economics"]
    sidecar_path(pdl).write_text(yaml.safe_dump(doc))
    assert build_roster(pdl)


@pytest.mark.parametrize("document", ["[]", "null", "scalar"])
def test_invalid_sidecar_root(tmp_path, document):
    pdl = configured_pdl(tmp_path, {})
    sidecar_path(pdl).write_text(document)
    with pytest.raises(ValueError, match="sidecar"):
        build_roster(pdl)


def test_exposure_rejects_dangling_inferred_dependency(tmp_path):
    pdl = configured_pdl(tmp_path, {"orchards": {
        "parameters": {"input_cost_shares": {"old_nutrients": .25}},
    }})
    doc = yaml.safe_load(sidecar_path(pdl).read_text())
    doc["dependencies"].append({"from": "orchards", "to": "old_nutrients_supply",
                                "type": "input"})
    sidecar_path(pdl).write_text(yaml.safe_dump(doc))
    with pytest.raises(ValueError, match="economics"):
        build_roster(pdl)
    # An explicit valid alias can repair that inferred dependency.
    doc["economics"]["orchards"]["bindings"] = {
        "old_nutrients": ["fertilizer_supply", "price"],
    }
    sidecar_path(pdl).write_text(yaml.safe_dump(doc))
    assert build_roster(pdl)


def test_configurator_template_preserves_freight_energy_response(monkeypatch):
    template = (Path(__file__).parents[1] / "web/src/configurator/templates"
                / "s1-soja.template.pdl.yaml")
    model = model_for(template, monkeypatch)
    routes = [entry for entry in model._roster
              if entry.archetype.role in ("land_transport", "sea_transport")]
    assert len(routes) == 8
    for entry in routes:
        route = getattr(model, entry.archetype.name).agents[0]
        assert route.binding["energy"] == ("gas_supply", "price")
    for name in model._execution_order:
        getattr(model, name).method_foreach("step", ())
    route = model.sea_transport_santos_port__rotterdam_port.agents[0]
    upstream = list(model.upstream(route.list_name))
    total = sum(source.quantity_available for source in upstream)
    input_price = sum(source.quantity_available * source.unit_price
                      for source in upstream) / total
    route.step()
    baseline_fee = route.unit_price - input_price
    model.environment.get_effective_value = (
        lambda entity, field: 2. if field == "price" else 1.
    )
    route.step()
    assert route.unit_price - input_price == pytest.approx(2 * baseline_fee)
