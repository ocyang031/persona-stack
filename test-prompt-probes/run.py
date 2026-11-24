import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from fixtures import FILES


ROOT = Path(__file__).resolve().parent
REPO = Path('D:/00_WY/400_Code/410_Remote/persona-stack')
LIVE = Path('D:/00_WY/300_Dev/.dsh')
TEMP = Path(tempfile.gettempdir())
SPEC = ROOT / 'PROBES.md'
MODEL = 'home-magpie/meoo/deepseek-v4.1-flash-1017'
ROUTE = ('magpie', MODEL, 'low')
ARMS = {'bare': None, 'minimal': 'aed40828ab97718e', 'full': 'b08ee5f92df2eaed'}
OFFLINE_ONLY = {'P01', 'P04'}
PROFILE_FILES = ('package.json', 'cordis.yml', 'cordis.patch.yml', 'pnpm-workspace.yaml')
STOCK = 'You are a coding agent powered by the {{model}} model.'


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_bytes(json_bytes(value))
    temp.replace(path)


def parse_probes():
    raw = SPEC.read_bytes()
    text = raw.decode('utf-8').replace('\r\n', '\n')
    rule = r'^## (P[0-9]{2}) · Full (.+)$'
    parts = re.split(rule, text, flags=re.M)
    probes = []
    for index in range(1, len(parts), 3):
        probe, sections, body = parts[index:index + 3]
        lines = [line for line in body.splitlines() if line.strip()]
        if not lines or any(not line.startswith('> ') or not line[2:].strip() for line in lines):
            raise ValueError(f'{probe}: use one nonempty quoted line per user turn')
        probes.append({'id': probe, 'fullSections': sections, 'turns': [line[2:] for line in lines]})
    if not probes or [p['id'] for p in probes] != [f'P{n:02d}' for n in range(1, len(probes) + 1)]:
        raise ValueError('Expected consecutive probe IDs beginning at P01')
    return digest(raw), probes


def live_plan(probes):
    return [dict(probe, cases=[], status='offline-only') if probe['id'] in OFFLINE_ONLY
            else dict(probe, cases=[]) for probe in probes]


def modules():
    base = REPO / 'bundles' / 'xiaoxiao'
    agents = {arm: (base / version / 'AGENTS.md').read_bytes().decode('utf-8') if version else ''
              for arm, version in ARMS.items()}
    excluded = [(base / version / name).read_bytes().decode('utf-8').strip()
                for version in ARMS.values() if version
                for name in ('SOUL.md', 'IDENTITY.md', 'TOOLS.md')]
    return agents, excluded


def inventory(folder, secret=None):
    output = {}
    for directory, subdirs, names in folder.walk():
        subdirs[:] = sorted(name for name in subdirs if name != '.git'
                            and not (directory / name).is_junction() and not (directory / name).is_symlink())
        for name in sorted(names):
            file = directory / name
            if name == '.dsh-prompt-debug.json' or file.is_symlink() or not file.is_file():
                continue
            data = file.read_bytes()
            if secret:
                data = data.replace(secret.encode(), b'[REDACTED_GATEWAY_CREDENTIAL]')
            output[file.relative_to(folder).as_posix()] = {
                'sha256': digest(data), 'base64': base64.b64encode(data).decode('ascii')}
    return output


def host_state():
    profile = LIVE / 'profiles' / 'dsh-tui'
    paths = [LIVE / 'cordis.patch.yml', LIVE / '.env', REPO / 'bindings.json',
             Path('D:/00_WY/100_Works/dsh-workspace/persona.prefix.txt')]
    paths += [profile / name for name in PROFILE_FILES]
    paths += [Path.home() / '.dsh-tui' / name for name in ('model.json', 'effort.json')]
    return {str(file): digest(file.read_bytes()) if file.is_file() else None for file in paths}


def overlay(agents):
    return [
        {'id': 'persona-preset-patch', 'config': {'preset': 'standard', 'config': {
            'persona': {'prefix': STOCK + ('\n\n' + agents if agents else '')}}}},
        {'id': 'agent-default-model', 'config': {'provider': ROUTE[0], 'model': ROUTE[1]}},
        {'id': 'mcp-chrome-devtools', 'disabled': True},
        {'id': 'magpie-mcp-calc', 'disabled': True},
    ]


def text_of(message):
    content = message.get('content', [])
    if isinstance(content, str):
        return content
    return ''.join(part.get('text', '') for part in content if part.get('type') == 'text')


def audit(context, arm, agents, excluded, turns):
    if context['turnCount'] != turns or len(context['turns']) != turns:
        raise ValueError('Unexpected number of captured turns')
    proofs = []
    for turn in context['turns']:
        if not turn['requests']:
            raise ValueError('A turn has no provider request')
        for request in turn['requests']:
            payload = request['finalLlmContext']
            if tuple(payload.get(key) for key in ('provider', 'model', 'reasoningEffort')) != ROUTE:
                raise ValueError('Unexpected provider, model or reasoning effort')
            system = '\n'.join(text_of(m) for m in payload['messages'] if m['role'] == 'system')
            for name, prompt in agents.items():
                if prompt and system.count(prompt.strip()) != int(arm == name):
                    raise ValueError('Incorrect AGENTS injection')
            if any(body in system for body in excluded):
                raise ValueError('Unexpected persona module in system prompt')
            native = system.replace(agents[arm].strip(), '', 1) if agents[arm] else system
            native = '\n'.join(line for line in native.splitlines() if line.strip())
            proofs.append({'nativeHash': digest(native.encode()),
                           'toolHash': digest(json_bytes(payload['tools']))})
    return proofs


def test_offline():
    spec_hash, probes = parse_probes()
    agents, excluded = modules()
    for arm, body in agents.items():
        system = overlay(body)[0]['config']['config']['persona']['prefix']
        payload = dict(provider=ROUTE[0], model=ROUTE[1], reasoningEffort=ROUTE[2],
                       messages=[dict(role='system', content=system)], tools=[])
        capture = {'turnCount': 1, 'turns': [{'requests': [{'finalLlmContext': payload}]}]}
        baseline = audit(capture, arm, agents, excluded, 1)
        for invalid_arm in set(agents) - {arm}:
            try:
                audit(capture, invalid_arm, agents, excluded, 1)
            except ValueError:
                pass
            else:
                raise AssertionError('Wrong-arm context was accepted')
        payload['messages'][0]['content'] += '\n' + excluded[0]
        try:
            audit(capture, arm, agents, excluded, 1)
        except ValueError:
            pass
        else:
            raise AssertionError('Excluded persona content was accepted')
        if not baseline:
            raise AssertionError('No proof generated')
    stale_fixtures = FILES.keys() - {probe['id'] for probe in probes}
    if stale_fixtures:
        raise ValueError(f'Fixtures for missing probes: {sorted(stale_fixtures)}')
    for fixtures in FILES.values():
        for name, body in fixtures.items():
            if name.endswith('.py'):
                compile(body, name, 'exec')
    total_turns = sum(len(probe['turns']) for probe in probes)
    offline_ids = ', '.join(probe['id'] for probe in live_plan(probes) if probe.get('status') == 'offline-only')
    print(f'Offline checks passed: {len(probes)} probes, {total_turns} turns, 3 arms.')
    print(f'Offline-only: {offline_ids or "none"}. PROBES.md SHA256: {spec_hash}')


def gateway_key():
    value = os.environ.get('MAGPIE_GATEWAY_KEY')
    if not value:
        for line in (LIVE / '.env').read_bytes().decode('utf-8-sig').splitlines():
            name, separator, value = line.partition('=')
            if separator and name.strip() == 'MAGPIE_GATEWAY_KEY':
                value = value.strip().strip('"').strip("'")
                break
        else:
            value = None
    if not value:
        raise RuntimeError('Magpie gateway key is unavailable')
    return value


def capture_json(data, secret):
    if isinstance(data, str):
        return data.replace(secret, '[REDACTED_GATEWAY_CREDENTIAL]')
    if isinstance(data, list):
        return [capture_json(item, secret) for item in data]
    if isinstance(data, dict):
        return {key: capture_json(value, secret) for key, value in data.items()}
    return data


class Tui:
    def __init__(self, engine, pty_dir, secret):
        sys.path.insert(0, str(pty_dir))
        from winpty import PtyProcess
        import zstandard

        self.pty = PtyProcess
        self.zstd = zstandard
        self.engine = engine
        self.node = shutil.which('node')
        self.secret = secret

    def prepare_profile(self, home):
        profile = home / 'profiles' / 'dsh-tui'
        profile.mkdir(parents=True)
        for name in PROFILE_FILES:
            shutil.copyfile(LIVE / 'profiles' / 'dsh-tui' / name, profile / name)
        shutil.copyfile(LIVE / 'cordis.patch.yml', home / 'cordis.patch.yml')
        shutil.copytree(LIVE / 'shared-policy', home / 'shared-policy',
                        ignore=shutil.ignore_patterns('tests', 'node_modules'))
        subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                        f"New-Item -ItemType Junction -Path '{profile / 'node_modules'}' "
                        f"-Target '{self.engine.parents[3]}' | Out-Null"], check=True)

    def run(self, case, probe, arm, agents, excluded, row, flush):
        outputs = case / 'workspace'
        sessions = case / 'sessions'
        preference = case / 'user' / '.dsh-tui'
        for directory in (outputs, sessions, preference):
            directory.mkdir(parents=True)
        dsh = case / 'dsh'
        self.prepare_profile(dsh)
        subprocess.run(['git', 'init', '--quiet', '--template=', str(outputs)], check=True)
        for name, content in FILES.get(probe['id'], {}).items():
            file = outputs / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(content.encode('utf-8'))
        save(preference / 'model.json', {'provider': ROUTE[0], 'model': ROUTE[1]})
        save(preference / 'effort.json', {'effort': ROUTE[2]})
        save(preference / 'onboarding.json', {'completed': True, 'version': 1})
        save(preference / 'lang.json', {'lang': 'en'})
        launch = case / 'overlay.json'
        save(launch, overlay(agents[arm]))
        row['inputFiles'] = inventory(outputs)
        row['status'] = 'running'
        flush()

        env = {name: value for name, value in os.environ.items() if name.upper() in {
            'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PROCESSOR_ARCHITECTURE',
            'NUMBER_OF_PROCESSORS', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMDATA'}}
        extra_temp = case / 'temp'
        extra_temp.mkdir()
        env.update(DSH_HOME=str(dsh), DSH_TUI_SESSION_ROOT=str(sessions),
                   USERPROFILE=str(preference.parent), APPDATA=str(preference.parent / 'AppData' / 'Roaming'),
                   LOCALAPPDATA=str(preference.parent / 'AppData' / 'Local'),
                   TEMP=str(extra_temp), TMP=str(extra_temp), MAGPIE_GATEWAY_KEY=self.secret)
        args = [self.node, str(self.engine), '--profile', 'dsh-tui', '--patch', str(launch)]
        proc = None
        chunks = []
        worker = None
        debug = outputs / '.dsh-prompt-debug.json'
        turns = probe['turns']
        try:
            proc = self.pty.spawn(args + ['--', turns[0]], cwd=str(outputs), env=env, dimensions=(36, 120))
            row['processClosed'] = False
            worker = threading.Thread(target=drain, args=(proc, chunks), daemon=True)
            worker.start()
            for index, turn in enumerate(turns, start=1):
                if index > 1:
                    proc.write('\x1b[200~' + turn + '\x1b[201~')
                    time.sleep(1)
                    proc.write('\r')
                records = wait_for(lambda: self.finished(sessions, index), proc, 150)
                validate_turns(records, turns[:index], outputs)
            proc.write('/debug-prompt\r')
            capture = wait_for(lambda: read_json(debug), proc, 20)
            if capture['sessionId'] != records[0]['id']:
                raise ValueError('Prompt capture belongs to another session')
            row['requestContext'] = capture_json(capture, self.secret)
            proofs = audit(capture, arm, agents, excluded, len(turns))
            row['verification'] = {'exactInjection': True, 'excludedModulesAbsent': True, 'requests': proofs}
            row['status'] = 'completed'
        finally:
            try:
                if proc:
                    if proc.isalive() and row['status'] == 'completed':
                        proc.write('/exit\r')
                        deadline = time.monotonic() + 8
                        while proc.isalive() and time.monotonic() < deadline:
                            time.sleep(0.2)
                    if proc.isalive():
                        proc.close(force=True)
                    row['processClosed'] = not proc.isalive()
                if worker:
                    worker.join(timeout=2)
            finally:
                records = self.records(sessions)
                if records:
                    row['sessionId'] = records[0]['id']
                row['events'] = capture_json(records, self.secret)
                row['answers'] = capture_json([
                    {'turn': event['data'].get('turn'), 'text': text_of(event['data']['message'])}
                    for event in records if event['type'] == 'assistant/message'
                    and text_of(event['data']['message'])], self.secret)
                if 'requestContext' not in row:
                    row['requestContext'] = capture_json(read_json(debug), self.secret)
                    row['contextCapture'] = 'provider-debug' if row['requestContext'] else 'session-events-only'
                row['terminal'] = capture_json(''.join(chunks), self.secret)
                row['outputFiles'] = inventory(outputs, self.secret)
                flush()

    def records(self, sessions):
        files = list(sessions.rglob('session.v4.jsonl.zstd'))
        if len(files) > 1:
            raise RuntimeError('More than one session created for one comparison case')
        if not files:
            return []
        try:
            with files[0].open('rb') as encoded, self.zstd.ZstdDecompressor().stream_reader(
                encoded, read_across_frames=True
            ) as stream:
                return [json.loads(line) for line in stream.read().decode('utf-8').splitlines()]
        except (OSError, ValueError, self.zstd.ZstdError):
            return []

    def finished(self, sessions, count):
        records = self.records(sessions)
        return records if sum(event['type'] == 'turn/end' for event in records) >= count else None


def validate_turns(records, expected, workspace):
    header = records[0]
    if header.get('isSeeded') or Path(header['cwd']).resolve() != workspace.resolve():
        raise ValueError('Session was seeded or launched in another directory')
    actual = [text_of(event['data']) for event in records if event['type'] == 'user/message'
              and event['data'].get('source', {}).get('kind') == 'user']
    ends = [event['data']['reason']['kind'] for event in records if event['type'] == 'turn/end']
    if actual != expected or ends != ['completed'] * len(expected):
        raise ValueError('Session history or turn completion did not match the probe')
    if any(event['type'] == 'user/message'
           and event['data'].get('source', {}).get('kind') == 'agent-instructions'
           for event in records):
        raise ValueError('Unexpected workspace or global AGENTS loaded')


def read_json(path):
    try:
        return json.loads(path.read_bytes())
    except (FileNotFoundError, ValueError):
        return None


def drain(proc, chunks):
    try:
        while proc.isalive():
            chunks.append(proc.read(4096))
    except (OSError, EOFError):
        pass


def wait_for(check, proc, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        if not proc.isalive():
            raise RuntimeError('DSH TUI exited before evidence was captured')
        time.sleep(0.4)
    raise TimeoutError(f'Waited {seconds} seconds without expected evidence')


def blind_review(path):
    log = json.loads(path.read_bytes())
    return {'model': log['model'], 'probes': [
        {'id': probe['id'], 'turns': probe['turns'],
         **({'status': probe['status']} if 'status' in probe else {}), 'cases': [
            {key: case[key] for key in ('caseId', 'status', 'answers', 'inputFiles', 'outputFiles') if key in case}
            for case in sorted(probe['cases'], key=lambda item: item['caseId'])]}
        for probe in log['probes']]}


def execute(options):
    expected_root = REPO / 'test-prompt-probes'
    if ROOT != expected_root.resolve():
        raise RuntimeError(f'Live runs must start inside {expected_root}')
    spec_hash, probes = parse_probes()
    if options.approved_sha256 != spec_hash:
        raise RuntimeError('Probe hash is missing or differs from the reviewed PROBES.md')
    probes = live_plan(probes)
    runnable = [probe for probe in probes if probe.get('status') != 'offline-only']
    if not runnable:
        raise RuntimeError('No runnable probes in this set')
    engine = options.engine.resolve(strict=True)
    pty_dir = options.pty_dir.resolve(strict=True)
    version = subprocess.check_output(['node', str(engine), '--version'], text=True).strip()
    if version != '0.2.2-rc.1':
        raise ValueError(f'Unexpected DSH core version: {version}')
    agents, excluded = modules()
    before = host_state()
    secret = gateway_key()
    run_id = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    run_dir = ROOT / 'runs' / run_id
    run_dir.mkdir(parents=True)
    log = {'runId': run_id, 'model': {'provider': ROUTE[0], 'id': MODEL, 'effort': ROUTE[2]},
           'probeSha256': spec_hash, 'core': version, 'status': 'starting', 'probes': probes,
           'restore': {'strategy': 'isolated copy and process closure', 'hostBefore': before}}
    mappings = {}
    session_ids = set()
    native_contexts = None
    order = list(agents)
    random.SystemRandom().shuffle(order)
    for index, probe in enumerate(runnable):
        probe['cases'] = [{'caseId': uuid.uuid4().hex[:12], 'status': 'pending'} for _ in agents]
        for case, arm in zip(probe['cases'], order[index % 3:] + order[:index % 3]):
            mappings[case['caseId']] = {'arm': arm, 'bundle': ARMS[arm]}
    flush = lambda: save(run_dir / 'evidence.json', log)
    save(run_dir / 'group-key.review-after-scoring.json', mappings)
    flush()
    try:
        tui = Tui(engine, pty_dir, secret)
        for probe in runnable:
            for case in probe['cases']:
                case_id = case['caseId']
                try:
                    tui.run(run_dir / 'runtime' / case_id, probe, mappings[case_id]['arm'],
                            agents, excluded, case, flush)
                    if not case['processClosed'] or case['sessionId'] in session_ids:
                        raise RuntimeError('Fresh session or process closure could not be verified')
                    session_ids.add(case['sessionId'])
                    proof = case['verification']['requests']
                    observed = {(item['nativeHash'], item['toolHash']) for item in proof}
                    if len(observed) != 1 or native_contexts is not None and observed != native_contexts:
                        raise RuntimeError('Native system prompt or tool definitions changed')
                    native_contexts = observed
                except BaseException:
                    case['status'] = 'incomplete'
                    raise
                flush()
        log['status'] = 'completed'
    except BaseException as error:
        log['status'] = 'stopped'
        log['error'] = capture_json(f'{type(error).__name__}: {error}', secret)
        print(log['error'], file=sys.stderr)
    finally:
        after = host_state()
        log['restore'].update(hostAfter=after, hostUnchanged=(before == after),
                              processesClosed=all(case.get('processClosed', True)
                                                  for probe in probes for case in probe['cases']))
        if before != after or not log['restore']['processesClosed']:
            log['status'] = 'restoration-unverified'
        flush()
        print(run_dir / 'evidence.json')
    return 0 if log['status'] == 'completed' else 1


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('check')
    view = commands.add_parser('blind-view')
    view.add_argument('evidence', type=Path)
    live = commands.add_parser('run')
    live.add_argument('--approved-sha256', required=True)
    live.add_argument('--engine', type=Path,
                      default=TEMP / 'dsh-agents-rc1-tooling/node_modules/@deepseek-ai/dsh/lib/bin.js')
    live.add_argument('--pty-dir', type=Path, default=TEMP / 'dsh-agents-pty-lib')
    options = parser.parse_args()
    if options.action == 'check':
        test_offline()
        return 0
    if options.action == 'blind-view':
        sys.stdout.buffer.write(json_bytes(blind_review(options.evidence)))
        return 0
    return execute(options)


if __name__ == '__main__':
    raise SystemExit(main())
