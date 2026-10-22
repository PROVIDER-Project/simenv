"""Feed traders split their output across their own recipients only."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from provider_simenv.model import SupplyChainModel
from provider_simenv.pdl_loader import PDLLoader
from provider_simenv.scenario import SupplyChainScenario
from provider_simenv.topology import build_flow_adjacency

SCENARIOS = Path(__file__).resolve().parents[1] / "src" / "provider_simenv" / "scenarios"
PDL = SCENARIOS / "s1-soja.pdl.yaml"
ROSTER = SCENARIOS / "s1-soja.roster.yaml"

GERMAN_MILLS = (
    "  - id: de_oil_mills\n"
    "    type: manufacturer\n"
    '    name: "DE oil mills"\n'
    "    sector: processing\n"
    "    location: Germany\n"
    "    vulnerability: 0.5\n"
    "\n"
    "  - id: de_feed_mills\n"
    "    type: manufacturer\n"
    '    name: "DE feed mills"\n'
    "    sector: processing\n"
    "    location: Germany\n"
    "    vulnerability: 0.6\n"
    "\n"
)
GERMAN_TRADER = (
    "  - id: de_feed_trader\n"
    '    name: "DE feed distributor"\n'
    "    archetype: feed_trader\n"
    '    reason: "second, independent feed chain"\n'
)


def _replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _two_feed_chains(tmp_path: Path) -> Path:
    pdl = PDL.read_text(encoding="utf-8")
    pdl = _replace_once(pdl, "  - id: feed_mills\n", GERMAN_MILLS + "  - id: feed_mills\n")
    pdl = _replace_once(
        pdl,
        "      - [hamburg_port, eu_oil_mills]\n",
        "      - [hamburg_port, de_oil_mills]\n"
        "      - [de_oil_mills, de_feed_mills]\n",
    )
    roster = ROSTER.read_text(encoding="utf-8")
    roster = _replace_once(
        roster,
        "  feed_mills:       feed_manufacturer\n",
        "  feed_mills:       feed_manufacturer\n"
        "  de_oil_mills:     processor\n"
        "  de_feed_mills:    feed_manufacturer\n",
    )
    roster = _replace_once(
        roster,
        "  - id: eu_feed_trader\n",
        GERMAN_TRADER + "  - id: eu_feed_trader\n",
    )
    roster = _replace_once(
        roster,
        "  - [eu_feed_trader, dairy_farms]\n",
        "  - [de_feed_mills, de_feed_trader]\n"
        "  - [de_feed_trader, dairy_farms]\n",
    )
    path = tmp_path / PDL.name
    path.write_text(pdl, encoding="utf-8")
    (tmp_path / ROSTER.name).write_text(roster, encoding="utf-8")
    return path


def _first_step(pdl: Path, monkeypatch) -> SupplyChainModel:
    monkeypatch.setattr(SupplyChainModel, "_pdl_path", str(pdl), raising=False)
    monkeypatch.setattr(
        SupplyChainModel, "_event_registry",
        PDLLoader(pdl).to_event_registry(None), raising=False,
    )
    model = SupplyChainModel(SimpleNamespace(), SupplyChainScenario(1))
    model._setup()
    model._init_event_tracker()
    model._do_step(0)
    return model


def test_independent_feed_chains_split_per_trader(tmp_path, monkeypatch):
    pdl = _two_feed_chains(tmp_path)
    adjacency = build_flow_adjacency(pdl)
    assert adjacency["poultry_farms"] == ("eu_feed_trader",)
    assert adjacency["pig_farms"] == ("eu_feed_trader",)
    assert adjacency["dairy_farms"] == ("de_feed_trader",)

    model = _first_step(pdl, monkeypatch)
    eu_feed = model.eu_feed_trader.agents[0].quantity_available
    de_feed = model.de_feed_trader.agents[0].quantity_available
    assert eu_feed > 0 and de_feed > 0

    poultry = model.poultry_farms.agents[0].feed_received
    pigs = model.pig_farms.agents[0].feed_received
    dairy = model.dairy_farms.agents[0].feed_received
    assert poultry == pytest.approx(eu_feed / 2)
    assert pigs == pytest.approx(eu_feed / 2)
    assert dairy == pytest.approx(de_feed)
    assert poultry + pigs + dairy == pytest.approx(eu_feed + de_feed)
