"""Real Windows H fixture worker evidence; no live DB, HTTP or request payloads."""
import asyncio
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import ctypes as C
from ctypes import wintypes as W
from dataclasses import asdict
from datetime import datetime
from unittest.mock import patch

import pytest

from app.analytics.offline_fixture import (CASES, FixtureError, INPUT_LIMIT,
    calculate, fixture_payload, stable, validate_payload)
from app.analytics.offline_spike import FixtureSpike, MEMORY_LIMIT
from app.analytics.process_isolation import IsolationError, kernel

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows worker evidence only')


def clean(gate, count):
    assert not gate.tasks and not gate.active
    assert len(gate.receipts) == count
    k = kernel()
    k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k.OpenProcess.restype = W.HANDLE
    for pid, code, _ in gate.receipts:
        assert type(code) is int
        handle = k.OpenProcess(0x100000, False, pid)
        if handle:
            try:
                assert k.WaitForSingleObject(handle, 0) == 0
            finally:
                k.CloseHandle(handle)


@pytest.mark.parametrize('case', CASES)
def test_real_h_all_kpi_identity_denominator_policy_parity(case):
    async def exercise():
        payload = fixture_payload(case)
        direct = calculate(payload)
        from app.analytics.service import HistoryEvent, HistoryPopulation, aggregate_history
        from app.analytics.deadlines import DeadlineWindow
        context = payload['context']
        trusted = aggregate_history(HistoryPopulation(7, 33,
            tuple(HistoryEvent(**e) for e in payload['events']), 1, context['as_of'],
            1, 'complete_observed_storage', context['start'], context['end']),
            window=DeadlineWindow(datetime.fromisoformat(context['as_of']), 'Europe/Rome', 7, 'Europe/Rome'),
            current_profile_digest=context['profile_digest'],
            selected_identities=None if payload['selected_identities'] is None else
                frozenset(tuple(i) for i in payload['selected_identities']))
        assert stable(direct['kpis']) == stable({k: asdict(v) for k, v in trusted['kpis'].items()})
        for field in ('population_id', 'U', 'unknown_fit', 'current_fit_unknown', 'selected_events'):
            assert stable(direct[field]) == stable(trusted[field])
        gate = FixtureSpike()
        try:
            child = await gate.run(case)
            assert child['pid'] != os.getpid()
            assert stable(child['result']) == stable(direct)
            assert set(direct['kpis']) == {'Discovered', 'Matched', 'High Fit',
                                         'Active Sources', 'Countries', 'Closing Soon'}
            assert direct['scope'] == [7, 33] and direct['origin'] == 'H'
            assert direct['context'] == payload['context']
            assert direct['sample_window'] == [payload['context']['start'], payload['context']['end']]
            assert direct['selected_identities'] == payload['selected_identities']
            assert len(direct['population_id']) == 64
            assert direct['deadline_grouping']['timezone_status'] == 'available'
            if case == 'normal':
                assert {k: v['value'] for k, v in direct['kpis'].items()} == {
                    'Discovered': 4, 'Matched': 2, 'High Fit': 2,
                    'Active Sources': 1, 'Countries': 1, 'Closing Soon': 1}
                assert direct['fit_bands']['low']['numerator'] == 1
                assert direct['fit_bands']['low']['denominator'] == 3
                assert direct['closing_soon_date_only']['identities'] == [['ted', 'calendar']]
            if case == 'empty':
                assert direct['kpis']['Discovered']['value'] == 0
                assert direct['kpis']['Countries']['value'] == 0
            if case == 'unknown':
                assert direct['kpis']['Matched']['value'] is None
                assert direct['kpis']['Matched']['denominator'] == 0
                assert direct['unknown_fit']
            if case in ('legacy', 'foreign', 'future'):
                assert all(row['current_band'] == 'unknown' for row in direct['fits'])
                assert direct['current_fit_unknown']
            if case == 'filtered':
                assert direct['U'] == [['ted', 'zero']]
                assert direct['kpis']['High Fit']['value'] == 0
            assert gate.peaks[0]['peak_commit'] < MEMORY_LIMIT
            evidence = Path('.cache/phase24p3/p39d-memory.jsonl')
            evidence.parent.mkdir(parents=True, exist_ok=True)
            with evidence.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'case': case, **gate.peaks[0]}) + '\n')
        finally:
            await gate.shutdown()
        clean(gate, 1)
    asyncio.run(exercise())


@pytest.mark.parametrize('mutation', ['version', 'bool_version', 'org', 'company', 'event_org',
    'duplicate_event', 'overflow', 'extra', 'credential', 'profile', 'timezone', 'as_of',
    'start', 'end', 'filter', 'score', 'provenance', 'population_id'])
def test_fail_closed_only_pinned_offline_data(mutation):
    value = copy.deepcopy(fixture_payload('normal'))
    if mutation == 'version': value['v'] = 2
    elif mutation == 'bool_version': value['v'] = True
    elif mutation in ('org', 'company'):
        value['context']['organization_id' if mutation == 'org' else 'company_id'] += 1
    elif mutation == 'event_org': value['events'][0]['organization_id'] += 1
    elif mutation == 'duplicate_event': value['events'] *= 2
    elif mutation == 'overflow': value['events'][0]['id'] = 2 ** 100
    elif mutation == 'extra': value['trusted_membership'] = True
    elif mutation == 'credential': value['api_key'] = 'synthetic-not-a-secret'
    elif mutation == 'profile': value['context']['profile_digest'] = 'a' * 64
    elif mutation == 'timezone': value['context']['timezone'] = 'UTC'
    elif mutation == 'as_of': value['context']['as_of'] = '9999-12-31T23:59:59+00:00'
    elif mutation in ('start', 'end'): value['context'][mutation] = None
    elif mutation == 'filter': value['selected_identities'] = [['ted', 'high']]
    elif mutation == 'population_id': value['population_id'] = 'untrusted'
    else:
        body = json.loads(value['events'][0]['snapshot_json'])
        if mutation == 'score': body['items'][0]['preliminary_scoring']['fit_score'] = 90
        else: body['items'][0]['preliminary_provenance']['organization_id'] = 999
        value['events'][0]['snapshot_json'] = json.dumps(body)
    with pytest.raises(FixtureError, match='^invalid_fixture_input$'):
        validate_payload(stable(value))


@pytest.mark.parametrize('raw', [b'{', b'[]', b'{"v":1,"v":1}', b'{"v":NaN}',
    b'\xff', b'x' * (INPUT_LIMIT + 1), b'[' * 1000],
    ids=['syntax', 'array', 'duplicate', 'nonfinite', 'utf8', 'oversize', 'depth'])
def test_malformed_duplicate_nonfinite_oversize(raw):
    with pytest.raises(FixtureError, match='^invalid_fixture_input$'):
        validate_payload(raw)


def test_fixture_commitment_and_no_spawn_for_wrong_scope():
    async def exercise():
        gate = FixtureSpike()
        with patch('app.analytics.offline_spike.subprocess.Popen', side_effect=AssertionError('spawned')):
            with pytest.raises(FixtureError, match='fixture_only'):
                await gate.run('client-controlled-history')
            with patch('app.analytics.offline_fixture.FIXTURE_SHA256', '0' * 64):
                with pytest.raises(FixtureError, match='fixture_commitment'):
                    await gate.run()
        await gate.shutdown()
        clean(gate, 0)
    asyncio.run(exercise())


@pytest.mark.parametrize('raw', [b'{', b'x' * (INPUT_LIMIT + 1),
    stable({'v': 2}), stable({'v': 1, 'case': 'normal', 'trusted_membership': True})],
    ids=['syntax', 'oversize', 'version', 'trust_claim'])
def test_real_child_rejects_corrupt_pipe_redacted_and_reaped(raw):
    # Inject transport corruption AFTER genuine parent fixture checks. No security
    # check is disabled in the worker; actual Job controls remain installed.
    original = subprocess.Popen
    class Pipe:
        def __init__(self, stream): self.stream = stream
        def write(self, _): return self.stream.write(raw)
        def close(self): return self.stream.close()
    def corrupt(*args, **kw):
        process = original(*args, **kw)
        process.stdin = Pipe(process.stdin)
        return process
    async def exercise():
        gate = FixtureSpike()
        try:
            with patch('app.analytics.offline_spike.subprocess.Popen', corrupt):
                with pytest.raises(IsolationError, match='^child_exit$'):
                    await gate.run()
        finally:
            await gate.shutdown()
        clean(gate, 1)
    asyncio.run(exercise())


def test_real_timeout_initialized_fixture_child_kill_wait_reap():
    async def exercise():
        gate, ready = FixtureSpike(), asyncio.Event()
        try:
            with pytest.raises(IsolationError, match='^deadline$'):
                await gate.run(hold=True, started=ready, seconds=2)
            assert ready.is_set()
        finally:
            await gate.shutdown()
        clean(gate, 1)
        assert gate.receipts[0][1] != 0
    asyncio.run(exercise())


def test_barrier_cancel_capacity_shutdown_and_slot_reuse():
    async def exercise():
        gate, ready = FixtureSpike(), asyncio.Event()
        task = asyncio.create_task(gate.run(hold=True, started=ready))
        try:
            await asyncio.wait_for(ready.wait(), 4)
            process = next(iter(gate.active.values()))
            with pytest.raises(IsolationError, match='capacity'):
                await gate.run()
            task.cancel()
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            assert process.returncode is not None
            clean(gate, 1)
            await gate.run('empty')
        finally:
            await gate.shutdown()
            await asyncio.gather(task, return_exceptions=True)
        clean(gate, 2)
    asyncio.run(exercise())


def test_cancel_before_start_no_child():
    async def exercise():
        gate = FixtureSpike()
        task = asyncio.create_task(gate.run())
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        await gate.shutdown()
        clean(gate, 0)
    asyncio.run(exercise())


def test_stable_json_repeated_real_calculation():
    async def exercise():
        gate = FixtureSpike()
        try:
            first = await gate.run()
            second = await gate.run()
            assert stable(first['result']) == stable(second['result'])
        finally:
            await gate.shutdown()
        clean(gate, 2)
    asyncio.run(exercise())


def test_shutdown_initialized_child_is_reaped_and_gate_closed():
    async def exercise():
        gate, ready = FixtureSpike(), asyncio.Event()
        task = asyncio.create_task(gate.run(hold=True, started=ready))
        try:
            await asyncio.wait_for(ready.wait(), 4)
            await gate.shutdown()
            with pytest.raises(asyncio.CancelledError): await task
            clean(gate, 1)
            with pytest.raises(IsolationError, match='capacity'): await gate.run()
        finally:
            await gate.shutdown()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(exercise())


def test_assignment_failure_owned_fixture_child_cleanup():
    async def exercise():
        gate = FixtureSpike()
        def failing_kernel():
            k = kernel()
            k.AssignProcessToJobObject = lambda *args: False
            return k
        try:
            with patch('app.analytics.offline_spike.kernel', failing_kernel):
                with pytest.raises(IsolationError, match='^assign_job_winerror_'):
                    await gate.run()
        finally:
            await gate.shutdown()
        clean(gate, 1)
    asyncio.run(exercise())
