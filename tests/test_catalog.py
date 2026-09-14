"""Task review is a projection of repository files, never an evaluation run."""

import json
import re
import shutil
import subprocess
from pathlib import Path

from expo_harbor_evals.catalog import build_catalog, build_html
from expo_harbor_evals.viewer import render_index

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = "feedback-12-native-fixed-amount-column"


def copy_task_fixture(repo):
    task = repo / "tasks/codegen" / LAYOUT
    shutil.copytree(ROOT / "tasks/codegen" / LAYOUT, task)
    for name in ["tests/contracts/run-controls.mjs", "tests/contracts/render-fixture.mjs", "tests/test_native_contracts.py"]:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return task


def catalog_data(document):
    payload = re.search(r'<script\b(?=[^>]*id="catalog-data")[^>]*>(.*?)</script>', document, re.S)
    return json.loads(payload[1])


def test_catalog_projects_every_task_and_keeps_measurements_separate():
    data = build_catalog(ROOT)
    definitions = {path.parent.name for path in (ROOT / "tasks").rglob("task.toml")}
    assert {task["id"] for task in data["tasks"]} == definitions
    assert len(data["tasks"]) == 28
    assert sum(task["family"] == "expo-codegen" for task in data["tasks"]) == 21
    assert sum(bool(task["native"]) for task in data["tasks"]) == 3
    new = next(task for task in data["tasks"] if task["id"] == LAYOUT)
    assert new["validation"] == "source-calibration-failed"
    assert not new["native"]
    assert len(new["criteria"]) == 4
    assert new["reviews"][0]["findings"][0]["decision"] == "added"


def test_catalog_retains_load_bearing_vendored_fixture_and_hides_duplicates():
    slider = next(task for task in build_catalog(ROOT)["tasks"] if task["id"].startswith("feedback-05-"))
    files = {f["path"]: f for f in slider["files"]}
    wrapper = files["environment/node_modules/@react-native-community/slider/dist/Slider.js"]
    assert wrapper["role"] == "Starting app"
    assert "passedValue=Number.isNaN(value)||!value?undefined:value" in wrapper["content"]
    assert not any(path.startswith("tests/reference/") for path in files)
    assert not any(path.endswith("baseline-manifest.json") for path in files)


def test_portable_html_escapes_embedded_source_and_embeds_licensed_fonts(tmp_path):
    task = copy_task_fixture(tmp_path)
    attack = '</script><img src=x onerror="alert(1)">\u2028'
    (task / "instruction.md").write_text(attack)
    document = build_html(tmp_path)
    assert attack not in document
    assert catalog_data(document)["tasks"][0]["instruction"] == attack
    assert "data:font/woff2;base64," in document
    assert "SIL OPEN FONT LICENSE" in document
    assert "Copyright (c) 2023 Expo" in document
    assert not re.search(r'<script[^>]+src=', document)


def test_draft_revision_changes_with_prompt_or_control(tmp_path):
    task = copy_task_fixture(tmp_path)
    original = build_catalog(tmp_path)["tasks"][0]["revision"]
    control = task / "solution/reference/summaryStyles.ts"
    control.write_text(control.read_text() + "\n// revised control\n")
    updated = build_catalog(tmp_path)["tasks"][0]["revision"]
    assert updated != original
    authoring_check = tmp_path / "tests/contracts/run-controls.mjs"
    authoring_check.write_text(authoring_check.read_text() + "\n// revised check\n")
    assert build_catalog(tmp_path)["tasks"][0]["revision"] != updated


def test_filter_and_copy_context_use_current_task_data():
    script = r"""
const assert = require('node:assert/strict');
const {matchingTasks, controlSummary, reviewContext, escapeHtml} = require('./src/expo_harbor_evals/web/catalog.js');
const data = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const task = data.tasks.find(t => t.id === 'feedback-12-native-fixed-amount-column');
assert.equal(controlSummary(task).references, 2); // solve.sh is not a third valid design.
assert.equal(controlSummary(task).negative, true);
const device = data.tasks.find(t => t.family === 'simbench');
assert.equal(controlSummary(device).references, 1);
assert.deepEqual(matchingTasks(data.tasks, {query:'112 amount', category:'expo-feedback'}).map(t=>t.id), [task.id]);
assert.equal(matchingTasks(data.tasks, {family:'simbench', native:true}).length, 0);
assert.equal(matchingTasks(data.tasks, {query:'impossible-query'}).length, 0);
const context = reviewContext(task, 'A proposed prompt', 'Keep the mask accessible.', data.repository);
for (const content of ['A proposed prompt', 'Keep the mask accessible.', task.instruction, task.revision, task.criteria[0].description, task.path+'/task.toml', 'solution/reference/summaryStyles.ts', '- tests/contracts/run-controls.mjs', 'source-calibration-failed', 'do not start model evaluations']) assert.ok(context.includes(content), content);
assert.equal(escapeHtml('<img onerror="x">'), '&lt;img onerror=&quot;x&quot;&gt;');
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, input=json.dumps(build_catalog(ROOT)),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_viewer_works_without_a_first_run_and_links_to_tasks(tmp_path):
    page = render_index(tmp_path / "no-runs-yet")
    assert 'href="/tasks"' in page
    assert "0 runs" in page
    assert "--expo-theme-text-default" in page


def test_detail_render_escapes_malformed_metadata():
    # Exercise the browser rendering entry point, not only escapeHtml itself.
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const task = data.tasks[0];
const attack = '\"><img src=x onerror=alert(1)>';
task.metadata.difficulty = attack;
task.criteria[0].weight = attack;
task.category = attack;
const elements = new Map();
const get = id => {
  if (!elements.has(id)) elements.set(id, {textContent:'', innerHTML:'', dataset:{}});
  return elements.get(id);
};
get('catalog-data').textContent = JSON.stringify(data);
vm.runInNewContext(fs.readFileSync('./src/expo_harbor_evals/web/catalog.js', 'utf8'), {
  document: {getElementById:get, querySelector:()=>({}), querySelectorAll:()=>[], documentElement:{dataset:{}}},
  location: {hash:'#task='+encodeURIComponent(task.id)},
  localStorage: {getItem:()=>null}, URLSearchParams,
  window: {addEventListener:()=>{}, scrollTo:()=>{}},
});
assert.ok(!get('main').innerHTML.includes('<img'));
assert.ok(get('main').innerHTML.includes('&lt;img'));
assert.ok(get('main').innerHTML.includes('#set='+encodeURIComponent(attack)));
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, input=json.dumps(build_catalog(ROOT)),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
