import hashlib
import json

import pandas as pd
import pytest
import yaml
from api_helpers import PDL, ROSTER
from fastapi.testclient import TestClient
from test_api import ManualQueue

from provider_simenv.api.app import create_app


@pytest.fixture
def inputs_client(tmp_path):
    with TestClient(create_app(tmp_path, queue_factory=ManualQueue)) as api:
        yield api


def job(api, tmp_path, roster=ROSTER):
    response = api.post('/simulations', json={'pdl': PDL, 'roster': roster})
    assert response.status_code == 202
    identity = response.json()['id']
    return identity, tmp_path / 'jobs' / identity


def complete(api, identity, directory):
    inputs = directory / 'input'
    rows = pd.read_csv(inputs / 'SimulatorScenarios_template.csv')
    executed = rows[rows.id == 0].copy()
    executed['id'] = 1
    executed.to_csv(inputs / 'SimulatorScenarios.csv', index=False)
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    roster = inputs / 'scenario.roster.yaml'
    manifest = {'runs': [{
        'run_id': identity,
        'pdl_sha256': digest(inputs / 'scenario.pdl.yaml'),
        'roster_sha256': digest(roster) if roster.exists() else None,
    }]}
    (directory / 'output/runs.json').write_text(json.dumps(manifest))
    api.app.state.store.finish(identity, status='completed')


@pytest.mark.parametrize('roster', [ROSTER, None])
def test_inputs_expose_preserved_documents_and_parameters(
    inputs_client, tmp_path, roster,
):
    identity, _ = job(inputs_client, tmp_path, roster)
    response = inputs_client.get(f'/simulations/{identity}/inputs')
    assert response.status_code == 200
    data = response.json()
    assert data['pdl'] == yaml.safe_load(PDL)
    assert data['roster'] == (yaml.safe_load(roster) if roster else None)
    assert data['cascade'] == 'soy_crisis_cascade'
    assert data['parameters'] == data['current_parameters']
    assert data['parameters']['farm_size_seed'] == 42
    assert 'id' not in data['parameters']
    assert data['evidence'] == 'preserved'
    assert inputs_client.get('/simulations/missing/inputs').status_code == 404


def test_completed_inputs_require_execution_evidence(inputs_client, tmp_path):
    identity, directory = job(inputs_client, tmp_path)
    complete(inputs_client, identity, directory)
    url = f'/simulations/{identity}/inputs'
    assert inputs_client.get(url).json()['evidence'] == 'execution-hashes'
    (directory / 'input/SimulatorScenarios.csv').unlink()
    assert inputs_client.get(url).status_code == 409


@pytest.mark.parametrize('damage', [
    'pdl', 'roster', 'manifest', 'missing-manifest', 'roster-absence',
    'parameters',
])
def test_inputs_reject_changed_or_corrupt_execution_evidence(
    inputs_client, tmp_path, damage,
):
    identity, directory = job(inputs_client, tmp_path,
                              None if damage == 'roster-absence' else ROSTER)
    complete(inputs_client, identity, directory)
    if damage in ('pdl', 'roster'):
        path = directory / f'input/scenario.{damage}.yaml'
        path.write_text(path.read_text() + '\n# changed\n')
    elif damage == 'manifest':
        (directory / 'output/runs.json').write_text('invalid JSON')
    elif damage == 'missing-manifest':
        (directory / 'output/runs.json').unlink()
    elif damage == 'roster-absence':
        (directory / 'input/scenario.roster.yaml').write_text(ROSTER)
    else:
        path = directory / 'input/SimulatorScenarios.csv'
        rows = pd.read_csv(path)
        rows['farm_size_seed'] = 99
        rows.to_csv(path, index=False)
    assert inputs_client.get(f'/simulations/{identity}/inputs').status_code == 409


def test_inputs_reject_non_json_yaml(inputs_client, tmp_path):
    identity, directory = job(inputs_client, tmp_path)
    path = directory / 'input/scenario.pdl.yaml'
    path.write_text(PDL + '\nunsupported: !!set {a: null}\n')
    assert inputs_client.get(f'/simulations/{identity}/inputs').status_code == 409


@pytest.mark.parametrize('damage', [
    'scenario-null', 'event-shape', 'id-null', 'id-number', 'id-empty',
    'id-space', 'integer-precision', 'large-document', 'large-csv-field',
])
def test_inputs_fail_closed_on_unrepresentable_or_malformed_sources(
    inputs_client, tmp_path, damage,
):
    identity, directory = job(inputs_client, tmp_path)
    path = directory / 'input/scenario.pdl.yaml'
    doc = yaml.safe_load(PDL)
    if damage == 'scenario-null':
        doc['scenario'] = None
    elif damage == 'event-shape':
        doc['events'] = ['invalid']
    elif damage.startswith('id-'):
        doc['cascades'][0]['id'] = {
            'id-null': None, 'id-number': 123, 'id-empty': '', 'id-space': ' ',
        }[damage]
    elif damage == 'integer-precision':
        template = directory / 'input/SimulatorScenarios_template.csv'
        rows = pd.read_csv(template)
        rows['farm_size_seed'] = 9007199254740992
        rows.to_csv(template, index=False)
        complete(inputs_client, identity, directory)
        executed = directory / 'input/SimulatorScenarios.csv'
        rows = pd.read_csv(executed)
        rows['farm_size_seed'] = 9007199254740993
        rows.to_csv(executed, index=False)
    elif damage == 'large-document':
        path.write_text(PDL + '\n#' + 'x' * (8 * 1024 * 1024))
    else:
        (directory / 'input/SimulatorScenarios_template.csv').write_text(
            'id,period_num\n0,' + '1' * 140000,
        )
    if damage in ('scenario-null', 'event-shape') or damage.startswith('id-'):
        path.write_text(yaml.safe_dump(doc))
    assert inputs_client.get(f'/simulations/{identity}/inputs').status_code == 409
