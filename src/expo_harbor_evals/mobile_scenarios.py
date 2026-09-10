"""Trusted native scenarios for the initial Expo candidate repair cohort."""

from __future__ import annotations

import json
import re
import time

from expo_harbor_evals.simbench_evidence import write_json


class Driver:
    def __init__(self, commands, session, output):
        self.commands, self.session, self.output = commands, session, output
        self.sequence = 0

    def command(self, *args):
        return self.commands.run(["agent-device", *args, "--session", self.session], timeout=60)

    def snapshot(self):
        raw = self.command("snapshot", "--json", "--force-full")
        data = json.loads(raw[raw.index("{"):])
        if data.get("success") is False or not isinstance(data.get("data", {}).get("nodes"), list):
            raise RuntimeError("Driver returned no accessibility tree")
        self.sequence += 1
        write_json(self.output / "screens" / f"{self.sequence:03d}.json", data)
        return data["data"]["nodes"]

    def find(self, predicate, *, seconds=12):
        deadline = time.monotonic() + seconds
        while True:
            matches = [node for node in self.snapshot() if predicate(node)]
            if len(matches) == 1:
                return matches[0]
            if time.monotonic() >= deadline:
                raise AssertionError(f"Expected one visible UI target, found {len(matches)}")
            time.sleep(0.4)

    def by_id(self, value):
        return self.find(lambda n: n.get("identifier") == value)

    def press(self, identifier):
        self.by_id(identifier)
        self.command("press", f'id="{identifier}"', "--settle")

    def fill(self, identifier, text):
        self.by_id(identifier)
        self.command("fill", f'id="{identifier}"', text, "--settle")

    def label(self, identifier):
        node = self.by_id(identifier)
        return str(node.get("label") or node.get("value") or "")

    def check(self, name, checks):
        self.command("screenshot", str(self.output / "screens" / f"{name}.png"))
        checks.append({"name": name, "passed": True})


def modal(driver, checks):
    driver.by_id("post-w1")
    for attempt in range(3):
        saved = f"Saved evaluation draft {attempt}"
        driver.press("post-w1")
        driver.press("edit-description")
        driver.fill("description-input", saved)
        driver.press("save-description")
        driver.press("close-detail")
        assert saved in driver.label("post-w1"), "Save did not update the feed"
        driver.check(f"save-and-return-{attempt}", checks)
        driver.press("post-w1")
        driver.press("edit-description")
        driver.fill("description-input", f"Discarded evaluation draft {attempt}")
        driver.press("cancel-description")
        driver.press("close-detail")
        assert saved in driver.label("post-w1"), "Cancel changed saved content"
        # A different card must open: visible feed text alone cannot establish
        # that the invisible modal/touch interception problem has gone away.
        driver.press("post-w2")
        assert "Wednesday" in driver.label("detail-title")
        driver.press("close-detail")
        driver.check(f"cancel-and-feed-interactive-{attempt}", checks)


def slider_fraction(node):
    value = str(node.get("value") or "")
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%\s*", value)
    if not match:
        # Fail as infrastructure, not an invented passing value, if the driver
        # stops exposing the native UISlider percentage.
        raise RuntimeError("Native slider percentage missing from accessibility evidence")
    return float(match[1]) / 100


def ev_value(driver):
    label = driver.label("exposure-readout")
    match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*EV", label)
    assert match, "EV readout missing"
    return float(match[1])


def slider(driver, checks):
    assert abs(ev_value(driver)) < 0.01
    for index, direction in enumerate((1, 1, -1, -1)):
        node = driver.by_id("exposure-control")
        assert abs(slider_fraction(node) - 0.5) <= 0.03, "Thumb did not return to its physical centre"
        rect = node["rect"]
        x, y = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2
        end = rect["x"] + (rect["width"] - 2 if direction > 0 else 2)
        before = ev_value(driver)
        driver.command("swipe", str(x), str(y), str(end), str(y), "650")
        # Poll the native value: a rendered constant value prop alone is not
        # sufficient evidence that the native thumb actually moved back.
        driver.find(lambda n: n.get("identifier") == "exposure-control"
                    and abs(slider_fraction(n) - 0.5) <= 0.03)
        after = ev_value(driver)
        assert abs(after - before - direction * 0.5) <= 0.06, "Released offset did not accumulate correctly"
        if index == 1:
            assert after > 0.5, "Running total was clamped to one nudge"
        driver.check(f"recenter-and-accumulate-{index}", checks)
    node = driver.by_id("exposure-control")
    rect = node["rect"]
    before = ev_value(driver)
    driver.command("press", str(rect["x"] + rect["width"] / 2),
                   str(rect["y"] + rect["height"] / 2), "--settle")
    assert abs(ev_value(driver) - before) <= 0.03, "Releasing at centre changed the total"
    assert abs(slider_fraction(driver.by_id("exposure-control")) - 0.5) <= 0.03
    driver.check("centre-release-is-neutral", checks)


def picker(driver, checks):
    driver.by_id("picker-empty")
    for attempt in range(2):
        driver.press("choose-image")
        # iOS's system photo picker owns these controls. English locale is a
        # prerequisite of this initial scenario and recorded as a limitation.
        driver.find(lambda n: n.get("label") == "Cancel")
        driver.command("press", 'label="Cancel"', "--settle")
        driver.by_id("picker-empty")
        driver.check(f"picker-cancel-{attempt}", checks)
    driver.press("choose-image")
    photo = driver.find(lambda n: "image" in str(n.get("type", "")).lower()
                        and "photo" in str(n.get("label", "")).lower())
    rect = photo["rect"]
    driver.command("press", str(rect["x"] + rect["width"] / 2),
                   str(rect["y"] + rect["height"] / 2), "--settle")
    driver.by_id("picker-preview")
    assert not any(n.get("identifier") == "picker-empty" for n in driver.snapshot()), "Preview retained empty state"
    driver.check("successful-image-selection-renders", checks)


SCENARIOS = {"modal": modal, "slider": slider, "picker": picker}
EXPECTED_CHECKS = {
    "modal": [name for i in range(3) for name in
              (f"save-and-return-{i}", f"cancel-and-feed-interactive-{i}")],
    "slider": [f"recenter-and-accumulate-{i}" for i in range(4)] + ["centre-release-is-neutral"],
    "picker": ["picker-cancel-0", "picker-cancel-1", "successful-image-selection-renders"],
}


def validate_result(result):
    """Reject a claimed pass without the complete, ordered scenario evidence."""
    if result.get("status") not in ("passed", "failed", "infra-error"):
        raise ValueError("Unknown native result status")
    if result.get("status") == "passed":
        checks = result.get("checks", [])
        required = ["candidate-build", *EXPECTED_CHECKS[result["input"]["profile"]]]
        if ([c.get("name") for c in checks] != required
                or any(c.get("passed") is not True for c in checks)
                or result.get("errors")):
            raise ValueError("Passing native result lacks complete scenario checks")


def run_scenario(profile, driver, checks):
    SCENARIOS[profile](driver, checks)
