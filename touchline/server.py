#!/usr/bin/env python3
"""Loopback dashboard server with a private match-summary service."""
import io
import json
import os
import re
import tempfile
import threading
from datetime import date, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from decision_analysis.input_adapter import public_profile
from decision_analysis.service import handle_get as decision_get, handle_post as decision_post
from decision.outcome import review_record
from decision.rollout import simulate
from decision.engine import analyze as analyze_decision, review as review_decision
from analysis_agent import build_report
from model_service import narrate, validate_base_url

ROOT = Path(__file__).resolve().parent
LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}
CONFIG = ROOT / '.local' / 'model-service.json'
LOCK = threading.Lock()

# The deployment lives in the environment, not in the repository, so a hosted
# instance needs no operator setup. The Settings page overrides these for a
# local session. The key never leaves the server: only whether one is
# configured is exposed.
DEFAULTS = {
    'base_url': os.environ.get('ITG_MODEL_BASE_URL', 'https://api.openai.com/v1'),
    'model': os.environ.get('ITG_MODEL_NAME', ''),
    'api_key': os.environ.get('ITG_MODEL_API_KEY', ''),
}

# A public demo entry is open to anyone, so the number of model calls it can
# make in a day is bounded. When the cap is spent the computed comparison
# still stands and the answer says the model is unavailable.
DAILY_CALL_CAP = int(os.environ.get('ITG_DAILY_CALL_CAP', '200'))
CALL_LOG = ROOT / '.local' / 'model-calls.json'

# A frozen snapshot plus the roster for that match. The roster carries the
# player profile, so a match frame runs about 25 KB.
MAX_REQUEST_BYTES = int(os.environ.get('ITG_MAX_REQUEST_BYTES', str(1024 * 1024)))


def claim_model_call():
    """Take one call slot for today, or refuse when the daily cap is spent."""
    today = date.today().isoformat()
    with LOCK:
        try:
            state = json.loads(CALL_LOG.read_text())
        except (OSError, ValueError):
            state = {}
        used = int(state.get(today, 0))
        if used >= DAILY_CALL_CAP:
            return False
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        state = {day: count for day, count in state.items() if day >= cutoff}
        state[today] = used + 1
        CALL_LOG.parent.mkdir(mode=0o700, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=CALL_LOG.parent, delete=False) as f:
            json.dump(state, f)
        os.replace(f.name, CALL_LOG)
        return True


def read_config():
    return {**DEFAULTS, **json.loads(CONFIG.read_text())} if CONFIG.exists() else DEFAULTS.copy()


def public_config(config):
    return {k: config[k] for k in ('base_url', 'model')} | {'has_key': bool(config['api_key'])}


def save_config(data):
    with LOCK:
        config = read_config()
        config['base_url'] = validate_base_url(data.get('base_url', config['base_url']))
        model = data.get('model', config['model'])
        key = data.get('api_key', '')
        if not isinstance(model, str) or not model.strip() or len(model) > 200:
            raise ValueError('Enter a model name.')
        if not isinstance(key, str) or len(key) > 4096 or any(c in key for c in '\r\n'):
            raise ValueError('Invalid API key.')
        if config['base_url'] != read_config()['base_url'] and not key.strip() and not data.get('clear_key'):
            raise ValueError('Enter the API key again when changing the service URL.')
        config['model'] = model.strip()
        if data.get('clear_key'):
            config['api_key'] = ''
        elif key.strip():
            config['api_key'] = key.strip()
        CONFIG.parent.mkdir(mode=0o700, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=CONFIG.parent, delete=False) as f:
            json.dump(config, f)
        os.replace(f.name, CONFIG)
        return public_config(config)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def allowed_hosts(self):
        """The hosts this server answers for.

        Loopback is always the operator's own machine, whatever port the server
        happens to run on. A hosted instance adds its public name through
        ITG_ALLOWED_HOSTS, so the same-origin rule still holds in production.
        """
        hosts = set()
        host = self.headers.get('Host', '')
        if host.split(':')[0] in LOOPBACK_HOSTS:
            hosts.add(host)
        for extra in os.environ.get('ITG_ALLOWED_HOSTS', '').split(','):
            extra = extra.strip()
            if extra:
                hosts.add(extra)
        return hosts

    def trusted(self):
        host = self.headers.get('Host', '')
        if host not in self.allowed_hosts():
            return False
        origin = self.headers.get('Origin')
        if not origin:
            return True
        return origin in (f'http://{host}', f'https://{host}')

    def reply(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_head(self):
        if not self.trusted():
            self.send_error(403)
            return None
        path = Path(self.translate_path(self.path)).resolve()
        relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else None
        if relative is None or any(p.startswith('.') for p in relative.parts):
            self.send_error(404)
            return None
        if relative.parts[:1] == ('public-demo',):
            self.send_error(410, 'Public Demo retired; open /index.html?view=decisions')
            return None
        if path.is_dir() and path != ROOT:
            self.send_error(404)
            return None
        if relative.parts[:1] == ('data',) and path.name in ('squads.json', 'metadata.json'):
            return self.send_redacted(path)
        return super().send_head()

    def send_redacted(self, path):
        """Roster files without the parts that identify a real person.

        The interface needs names, numbers and positions. It never needs the
        birth date, the source identifier or the capture fingerprint, and the
        source conflict records restate them, so none of those are served.
        """
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            return super().send_head()
        for player in self._players(payload):
            public = public_profile(player.get('sofascore'))
            if public is not None:
                player['sofascore'] = public
            player.pop('date_of_birth', None)
            player.pop('api_player_id', None)
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode() + b'\n'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        return io.BytesIO(body)

    @staticmethod
    def _players(payload):
        if not isinstance(payload, dict):
            return []
        if isinstance(payload.get('players'), list):
            return [p for p in payload['players'] if isinstance(p, dict)]
        return [p for team in payload.get('teams', []) if isinstance(team, dict)
                for p in team.get('players', []) if isinstance(p, dict)]

    def do_GET(self):
        if decision_get(self):return
        if urlsplit(self.path).path == '/api/model-settings':
            if not self.trusted():
                self.reply(403, {'error': 'Only same-origin local requests are accepted.'})
                return
            self.reply(200, public_config(read_config()))
        else:
            super().do_GET()

    def do_POST(self):
        if not self.trusted() or self.headers.get('Content-Type') != 'application/json':
            self.reply(403, {'error': 'Only same-origin JSON requests are accepted.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_REQUEST_BYTES:
                raise ValueError('Invalid request size.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            route = urlsplit(self.path).path
            if decision_post(self, route, data):return
            if route == '/api/rollout':
                self.reply(200, simulate(data['frame'], data['metadata'], data['action_id']))
                return
            if route == '/api/action-review':
                result = review_record(ROOT, data.get('dataset','league'), data.get('match_id',''), data.get('decision_id',''), data.get('replay_at_ms'))
                self.reply(200,result)
                return
            if route == '/api/decision':
                if data.get('mode', 'fan') not in ('fan', 'analyst'):
                    raise ValueError('Invalid audience mode.')
                report = analyze_decision(data['frame'], data['metadata'])
                self.reply(200, {**report, 'review': review_decision(report, data.get('mode', 'fan'))})
                return
            if route == '/api/model-settings':
                self.reply(200, save_config(data))
                return
            if route != '/api/match-summary':
                self.reply(404, {'error': 'Unknown endpoint.'})
                return
            match_id = data.get('match_id', '')
            if not isinstance(match_id, str) or not re.fullmatch(r'[A-Za-z0-9-]+', match_id):
                raise ValueError('Invalid match ID.')
            folder = ROOT / 'data' / 'league' / 'matches' / match_id
            if not folder.is_dir():
                raise ValueError('Match not found.')
            with LOCK:
                config = read_config()
            if not config['api_key'] or not config['model']:
                self.reply(400, {'error': 'Configure a model and API key in Settings first.'})
                return
            report = build_report(json.loads((folder / 'metadata.json').read_text()),
                                  json.loads((folder / 'summary.json').read_text()),
                                  [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines() if line.strip()])
            if report is None:
                raise ValueError('The match has not finished yet.')
            try:
                narrate(report, config['model'], config['api_key'], config['base_url'])
            except Exception:
                self.reply(502, {'error': 'Model service unavailable or returned an invalid report. Check your API key, model and service URL, then retry. Your existing report is unchanged.'})
                return
            with tempfile.NamedTemporaryFile(mode='w', dir=folder, suffix='.tmp', delete=False) as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            os.replace(f.name, folder / 'analysis.json')
            self.reply(200, report)
        except (ValueError, TypeError, KeyError, IndexError):
            self.reply(400, {'error': 'Invalid request. Check the snapshot, model settings or match ID.'})
        except Exception:
            self.reply(500, {'error': 'Unable to process the request.'})


if __name__ == '__main__':
    port=int(os.environ.get('TOUCHLINE_PORT','5173'))
    print(f'Touchline: http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
