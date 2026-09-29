"""Parity with the pinned toolkit and real, offline execution of every built-in."""
import ast
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import export_task
from kit_runner import programmatic_scores, validate_plan


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((export_task.KIT / 'catalog.json').read_text())
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.app = self.root / 'app'
        self.tests = self.root / 'tests'
        self.app.mkdir()
        (self.tests / 'checks').mkdir(parents=True)

    def test_catalog_covers_every_builtin_and_every_factory_argument(self):
        from rewardkit import criteria
        builtins = {r['builtin'] for key, r in self.catalog['checks'].items() if r['builtin'] and key != 'test-script'}
        self.assertEqual(builtins, set(criteria.__all__))
        for name in builtins:
            tree = ast.parse((Path(criteria.__file__).parent / f'{name}.py').read_text())
            fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
            parameters = {arg.arg for arg in fn.args.args} - {'workspace'}
            fields = {f['key'] for r in self.catalog['checks'].values() if r['builtin'] == name and r['label'] != 'Tests pass' for f in r['fields']}
            self.assertEqual(fields, parameters, name)

    def evaluate(self, kind, config, expected):
        definition = {'id': 'result', 'name': 'result', 'description': 'Fixture check', 'weight': 1}
        plan = {'schemaVersion': 1, 'checks': {'result': {'kind': kind, 'config': config}}}
        validate_plan(plan, [definition], self.catalog, self.tests)
        scores = programmatic_scores([definition], plan, self.catalog, self.app, self.tests)
        self.assertEqual(len(scores), 1)
        self.assertAlmostEqual(scores[0].value, expected, places=6, msg=kind)

    def test_every_check_executes_with_real_data_and_no_judge(self):
        from PIL import Image
        from openpyxl import Workbook
        (self.app / 'text.txt').write_text('hello')
        (self.app / 'same.txt').write_text('hello')
        (self.app / 'config.json').write_text('{"ready": true, "empty": null, "items": [{"name": "Expo"}]}')
        (self.app / 'table.csv').write_text('name,count\nExpo,3\n')
        with sqlite3.connect(self.app / 'data.db') as db:
            db.execute('CREATE TABLE notes (title TEXT)')
            db.execute("INSERT INTO notes VALUES ('Expo')")
        db.close()
        book = Workbook()
        book.active['A1'] = 'Expo'
        book.save(self.app / 'book.xlsx')
        image = Image.new('RGB', (4, 1), 'black')
        image.save(self.app / 'first.png')
        image.putpixel((2, 0), (255, 255, 255))
        image.putpixel((3, 0), (255, 255, 255))
        image.save(self.app / 'second.png')
        trajectory = {'steps': [{'source': 'agent', 'tool_calls': [{'function_name': 'inspect'}]}, {'source': 'agent'}, {'source': 'agent'}]}
        (self.tests / 'checks/trajectory.json').write_text(json.dumps(trajectory))
        (self.tests / 'checks/assert.py').write_text('import sys\nfrom pathlib import Path\nassert (Path(sys.argv[1]) / "text.txt").read_text() == "hello"\n')
        (self.tests / 'checks/custom.py').write_text('from rewardkit import criterion\n@criterion(shared=True)\ndef studio_custom(workspace):\n    return 0.75 if (workspace / "text.txt").exists() else 0\n')
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Expo ready')
            def log_message(self, *_):
                pass
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(close)
        url = f'http://127.0.0.1:{server.server_port}'
        cases = {
            'file-exists': ({'path': 'text.txt'}, 1),
            'file-not-exists': ({'path': 'absent'}, 1),
            'file-contains': ({'path': 'text.txt', 'text': 'ell'}, 1),
            'file-contains-regex': ({'path': 'text.txt', 'pattern': '^he[l]+o$'}, 1),
            'file-matches': ({'path': 'text.txt', 'expected': 'hello\n'}, 1),
            'files-equal': ({'path1': 'text.txt', 'path2': 'same.txt'}, 1),
            'diff-ratio': ({'path': 'text.txt', 'expected': 'hallo'}, 0.8),
            'json-key-equals': ({'path': 'config.json', 'key': 'ready', 'expected': 'true'}, 1),
            'json-path-equals': ({'path': 'config.json', 'json_path': 'items.0.name', 'expected': '"Expo"'}, 1),
            'csv-cell-equals': ({'path': 'table.csv', 'row': '0', 'col': '"name"', 'expected': 'Expo'}, 1),
            'xlsx-cell-equals': ({'path': 'book.xlsx', 'cell': 'A1', 'expected': '"Expo"'}, 1),
            'sqlite-query-equals': ({'db_path': 'data.db', 'query': 'SELECT COUNT(*) FROM notes', 'expected': '1'}, 1),
            'image-size-equals': ({'path': 'first.png', 'width': '4', 'height': '1'}, 1),
            'image-similarity': ({'path1': 'first.png', 'path2': 'second.png'}, 0.5),
            'http-status-equals': ({'url': url}, 1),
            'http-response-contains': ({'url': url, 'text': 'Expo'}, 1),
            'command-succeeds': ({'cmd': 'test -f text.txt'}, 1),
            'command-output-contains': ({'cmd': 'cat text.txt', 'text': 'ell'}, 1),
            'command-output-matches': ({'cmd': 'cat text.txt', 'expected': 'hello'}, 1),
            'command-output-matches-regex': ({'cmd': 'cat text.txt', 'pattern': '^hello$'}, 1),
            'trajectory-tool-used': ({'path': 'trajectory.json', 'tool_name': 'inspect'}, 1),
            'trajectory-tool-not-used': ({'path': 'trajectory.json', 'tool_name': 'delete'}, 1),
            'trajectory-turn-count': ({'path': 'trajectory.json', 'max_turns': '2'}, 0.5),
            'test-script': ({'script': 'assert.py'}, 1),
            'custom-python': ({'script': 'custom.py', 'factory': 'studio_custom'}, 0.75),
        }
        self.assertEqual(set(cases), set(self.catalog['checks']) - {'ai-review'})
        for kind, (config, expected) in cases.items():
            with self.subTest(kind=kind):
                self.evaluate(kind, config, expected)
        # Cover defaults, typed column indexes, and genuine failures as well as success fixtures.
        for kind, config in [
            ('command-succeeds', {'cmd': 'exit 1'}),
            ('file-not-exists', {'path': 'text.txt'}),
            ('json-path-equals', {'path': 'config.json', 'json_path': 'items.0.name', 'expected': '"Other"'}),
            ('image-size-equals', {'path': 'first.png', 'width': '5', 'height': '1'}),
            ('http-status-equals', {'url': url, 'status': '404'}),
            ('trajectory-tool-used', {'path': 'missing.json', 'tool_name': 'inspect'}),
            ('trajectory-tool-not-used', {'path': 'trajectory.json', 'tool_name': 'inspect'}),
            ('trajectory-turn-count', {'path': 'trajectory.json', 'max_turns': '1'}),
        ]:
            with self.subTest(failure=kind):
                self.evaluate(kind, config, 0)
        self.evaluate('csv-cell-equals', {'path': 'table.csv', 'row': '1', 'col': '0', 'expected': 'Expo'}, 1)
        self.evaluate('json-key-equals', {'path': 'config.json', 'key': 'empty', 'expected': 'null'}, 1)

    def test_invalid_config_is_rejected_before_execution(self):
        for kind, config in [
            ('command-succeeds', {'cmd': 'true', 'timeout': '0'}),
            ('command-succeeds', {'cmd': 'true', 'cwd': '../outside'}),
            ('image-size-equals', {'path': 'a.png', 'width': '1.5', 'height': '1'}),
            ('trajectory-turn-count', {'max_turns': '0'}),
            ('http-status-equals', {'url': 'file:///etc/passwd'}),
            ('csv-cell-equals', {'path': 'a.csv', 'row': '0', 'col': 'true', 'expected': 'yes'}),
            ('json-key-equals', {'path': 'a.json', 'key': 'x', 'expected': 'NaN'}),
            ('custom-python', {'script': '../escape.py', 'factory': 'check'}),
        ]:
            with self.subTest(kind=kind), self.assertRaises((ValueError, TypeError)):
                self.evaluate(kind, config, 1)
        (self.app / 'outside').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.evaluate('files-equal', {'path1': 'outside/private', 'path2': 'outside/private'}, 1)

    def test_trajectory_defaults_use_the_local_harbor_logs_directory(self):
        logs = self.root / '_local_env/logs'
        (logs / 'agent').mkdir(parents=True)
        trajectory = {'steps': [{'source': 'agent', 'tool_calls': [{'function_name': 'inspect'}]}]}
        (logs / 'agent/trajectory.json').write_text(json.dumps(trajectory))
        with patch.dict(os.environ, {'HARBOR_LOGS_DIR': str(logs)}):
            self.evaluate('trajectory-tool-used', {'tool_name': 'inspect'}, 1)
            self.evaluate('trajectory-tool-not-used', {'tool_name': 'delete'}, 1)
            self.evaluate('trajectory-turn-count', {'max_turns': '2'}, 1)
            (logs / 'agent/trajectory.json').unlink()
            self.evaluate('trajectory-tool-used', {'tool_name': 'inspect'}, 0)
