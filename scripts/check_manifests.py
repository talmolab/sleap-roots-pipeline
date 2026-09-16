#!/usr/bin/env python3
"""Executable assertions for the per-batch-pipeline spec's manifest-inspectable scenarios.

This repo has no CI and no unit-test harness, so every "Validate:" step in an OpenSpec change
has historically been prose that nobody could re-run. This script is the runnable form of the
scenarios in `openspec/specs/per-batch-pipeline/spec.md` (and the pending delta under
`openspec/changes/`) that can be checked by reading the manifests alone.

It deliberately does NOT replace `argo lint` — lint validates Argo schema and resolves
`templateRef`s; this validates the repo's own conventions, which lint knows nothing about
(priority classes, quota labels, credential isolation, retry shape, pin hygiene).

Usage:  python scripts/check_manifests.py        # from the repo root
Exit:   0 = all assertions hold, 1 = at least one failed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# A POSIX shell, for executing the gate's shipped script. Absence is a hard failure, never a
# skip: the gate assertions below are the only automated guard on this repo's central safety
# property, and a check whose failure mode is "everything is fine" is worse than no check.
SH = shutil.which("sh") or shutil.which("bash")

PIPELINE = "sleap-roots-pipeline.yaml"
GATE = "sleap-roots-exit-gate-template.yaml"
PRODUCERS = ["images-downloader", "predictor", "trait-extractor"]
BATCH_STAGES = {
    "images-downloader": "sleap-roots-images-downloader-template.yaml",
    "predictor": "sleap-roots-predictor-template.yaml",
    "trait-extractor": "sleap-roots-trait-extractor-template.yaml",
    "write-back": "sleap-roots-write-back-template.yaml",
}
ACCEPTED_GATE_CODES = {"0", "3"}

# Values the gate must reject, in every producer position. Each is a real failure mode:
# 1/2/99/143 are crash and SIGTERM exits; "" is a Failed node that produced no `outputs.exitCode`
# (a valid ancestor with no exit code -- the case Argo's own ancestry validator cannot catch);
# "03" and " 3" are near-misses the string compare must not normalise; the `{{tasks...}}`
# placeholder is what `template.Replace(..., allowUnresolved=true)` leaves behind; "*" and "x"
# probe for glob or arithmetic evaluation escaping the `case` subject.
REJECTED_GATE_CODES = [
    "1",
    "2",
    "99",
    "143",
    "-1",
    "",
    "03",
    " 3",
    "{{tasks.predictor.exitCode}}",
    "*",
    "x",
]

_failures: list[str] = []
_passes = 0


def gate_env_names(gate_ctr: dict) -> list[str]:
    """Map each producer to the gate env var carrying its exit code, in PRODUCERS order.

    Derived from the manifest rather than hardcoded, so renaming an env var or an input
    parameter makes the executable checks below follow it instead of silently going stale.
    """
    by_param = {
        e["value"]: e["name"] for e in gate_ctr.get("env", []) if isinstance(e.get("value"), str)
    }
    return [by_param[f"{{{{inputs.parameters.{p}-code}}}}"] for p in PRODUCERS]


def run_gate(script: str, env_names: list[str], codes: list[str | None]) -> int:
    """Execute the gate's SHIPPED script under `sh` and return its real exit status.

    `codes` is positional, matching PRODUCERS; a `None` entry leaves that variable *unset*,
    which is a distinct case from the empty string under the script's `set -u`.

    This runs the same two things the cluster runs -- the manifest's `command` (`/bin/sh -c`)
    and its `args[0]` -- so it cannot drift from the shipped gate the way a retyped copy or a
    substring check can. Env is deliberately minimal: nothing but PATH is inherited, so a
    variable the script reads can only come from `codes`.
    """
    env = {"PATH": os.environ.get("PATH", "")}
    for name, code in zip(env_names, codes):
        if code is not None:
            env[name] = code
    return subprocess.run(  # noqa: S603 - fixed argv, no shell, script comes from our own tree
        [SH, "-c", script],
        env=env,
        capture_output=True,
        text=True,
    ).returncode


def check(label: str, got, want) -> None:
    global _passes
    if got == want:
        _passes += 1
        print(f"PASS  {label}")
    else:
        _failures.append(f"{label}: got {got!r}, expected {want!r}")
        print(f"FAIL  {label}: got {got!r}, expected {want!r}")


def load(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def dag_tasks(wf: dict) -> list[dict]:
    return wf["spec"]["templates"][0]["dag"]["tasks"]


def main() -> int:
    wf = load(PIPELINE)
    gate = load(GATE)
    tasks = dag_tasks(wf)
    by_name = {t["name"]: t for t in tasks}
    gate_tmpl = gate["spec"]["templates"][0]
    gate_ctr = gate_tmpl["container"]

    # --- Requirement: Per-batch DAG with a terminal exit-code gate -------------------
    check("DAG has five tasks", len(tasks), 5)
    check(
        "DAG task order",
        [t["name"] for t in tasks],
        PRODUCERS + ["write-back", "exit-gate"],
    )
    check("no task uses depends", [t["name"] for t in tasks if "depends" in t], [])
    depended = {d for t in tasks for d in t.get("dependencies", [])}
    check(
        "exit-gate is the ONLY leaf",
        [t["name"] for t in tasks if t["name"] not in depended],
        ["exit-gate"],
    )
    check(
        "scan-ids parameter declared",
        len([p for p in wf["spec"]["arguments"]["parameters"] if p["name"] == "scan-ids"]),
        1,
    )
    check("serviceAccountName", wf["spec"].get("serviceAccountName"), "bloom-workflow")
    check(
        "hostPath volumes are type Directory",
        sorted({v["hostPath"]["type"] for v in wf["spec"]["volumes"] if "hostPath" in v}),
        ["Directory"],
    )

    # --- Requirement: A partial-success exit does not terminate the batch ------------
    check(
        "continueOn.failed on exactly the three producers",
        sorted(t["name"] for t in tasks if t.get("continueOn", {}).get("failed") is True),
        sorted(PRODUCERS),
    )
    check(
        "no task declares continueOn.error",
        [t["name"] for t in tasks if "error" in t.get("continueOn", {})],
        [],
    )
    check("write-back has no continueOn", "continueOn" in by_name["write-back"], False)
    for stage in PRODUCERS:
        tmpl = load(BATCH_STAGES[stage])["spec"]["templates"][0]
        check(f"{stage} retryPolicy is Always", tmpl["retryStrategy"].get("retryPolicy"), "Always")
        check(
            f"{stage} declares no retryStrategy.expression",
            "expression" in tmpl["retryStrategy"],
            False,
        )

    # --- Requirement: An exit-code gate determines the Workflow's final phase --------
    gate_task = by_name["exit-gate"]
    check("gate declares no when", "when" in gate_task, False)
    check(
        "gate passes three named parameters",
        len(gate_task["arguments"]["parameters"]),
        3,
    )
    refs = [
        re.fullmatch(r"\{\{tasks\.([\w-]+)\.exitCode\}\}", p["value"])
        for p in gate_task["arguments"]["parameters"]
    ]
    check("every gate parameter is an exitCode reference", all(refs), True)
    referenced = sorted(m.group(1) for m in refs if m)
    check("gate references exactly the three producers", referenced, sorted(PRODUCERS))

    # Every referenced producer must be an ANCESTOR of the gate. Argo enforces this too --
    # `validateDAGTaskArgumentDependency` rejects a non-ancestor reference at both `argo lint`
    # and submission (`missing dependency '<task>' for parameter '<name>'`), verified live -- so
    # this assertion is the earliest of three independent layers, not the only one. What neither
    # this check nor the validator can see is a task that IS a valid ancestor but produced no
    # `outputs.exitCode`; that case reaches the container as an empty or literal value, and only
    # the gate's allowlist (executed below) catches it.
    deps = {t["name"]: t.get("dependencies", []) for t in tasks}
    ancestors: set[str] = set()
    stack = list(deps["exit-gate"])
    while stack:
        n = stack.pop()
        if n not in ancestors:
            ancestors.add(n)
            stack.extend(deps.get(n, []))
    check("gate's referenced producers are all ancestors", sorted(set(referenced) - ancestors), [])

    # --- Requirement: The exit-gate template runs without data or credential access --
    check("gate templateRef name matches", gate["metadata"]["name"], gate_task["templateRef"]["name"])
    check("gate templateRef template matches", gate_tmpl["name"], gate_task["templateRef"]["template"])
    check("gate overrides command", "command" in gate_ctr, True)
    check("gate declares no volumeMounts", "volumeMounts" in gate_ctr, False)
    check("gate sets no HOME", [e for e in gate_ctr.get("env", []) if e["name"] == "HOME"], [])
    check("gate sets no template serviceAccountName", "serviceAccountName" in gate_tmpl, False)
    check("gate declares priorityClassName", bool(gate_tmpl.get("priorityClassName")), True)
    check("gate retryPolicy is Always", gate_tmpl["retryStrategy"].get("retryPolicy"), "Always")
    check(
        "gate retryStrategy declares a backoff duration",
        bool(gate_tmpl["retryStrategy"].get("backoff", {}).get("duration")),
        True,
    )
    check("gate declares resources.requests", "requests" in gate_ctr.get("resources", {}), True)
    check("gate carries a project label", gate["metadata"]["labels"].get("project"), "busch-lab")
    check(
        "gate declares three named inputs",
        len(gate_tmpl["inputs"]["parameters"]),
        3,
    )
    check(
        "gate input names match what the DAG passes",
        sorted(p["name"] for p in gate_tmpl["inputs"]["parameters"]),
        sorted(p["name"] for p in gate_task["arguments"]["parameters"]),
    )

    script = gate_ctr["args"][0]
    check(
        "gate script body is pure ASCII",
        [c for c in script if ord(c) > 127],
        [],
    )
    # The comparison must be an ALLOWLIST. A denylist would silently pass an unsubstituted
    # `{{tasks.X.exitCode}}` placeholder, an empty string, and any future exit code.
    #
    # This is asserted by EXECUTING the shipped script, not by inspecting its text. A substring
    # check cannot tell an allowlist from a denylist: `all(f"{c}|" in script ...)` is satisfied
    # by `0|1|3)` (which greens a crash) and by a full inversion to a denylist, both of which
    # were confirmed to pass while the gate accepted exit 99. Since this allowlist is the only
    # thing standing between a genuine crash and a green Workflow (#56), its guard has to run it.
    if not SH:
        check("POSIX shell available to execute the gate script", "not found", "sh or bash")
    else:
        env_names = gate_env_names(gate_ctr)
        accepted = sorted(ACCEPTED_GATE_CODES)
        check(
            "gate accepts every all-{0,3} combination of producer codes",
            [
                (a, b, c)
                for a in accepted
                for b in accepted
                for c in accepted
                if run_gate(script, env_names, [a, b, c]) != 0
            ],
            [],
        )
        check(
            "gate rejects every non-{0,3} code, in every producer position",
            [
                (i, bad)
                for i in range(len(PRODUCERS))
                for bad in REJECTED_GATE_CODES
                if run_gate(script, env_names, [bad if j == i else "0" for j in range(3)]) == 0
            ],
            [],
        )
        check(
            "gate rejects an unset producer code (a Failed node with no outputs.exitCode)",
            [
                i
                for i in range(len(PRODUCERS))
                if run_gate(script, env_names, [None if j == i else "0" for j in range(3)]) == 0
            ],
            [],
        )
    check(
        "gate reads codes from env, not interpolated into the script",
        "{{" in script,
        False,
    )

    # --- Requirement: Every producer carries the Argo workflow identity --------------
    for stage, fname in BATCH_STAGES.items():
        env = load(fname)["spec"]["templates"][0]["container"].get("env", []) or []
        entry = [e for e in env if e["name"] == "ARGO_WORKFLOW_NAME"]
        check(f"{stage} sets ARGO_WORKFLOW_NAME", len(entry), 1)
        if entry:
            check(f"{stage} ARGO_WORKFLOW_NAME value", entry[0].get("value"), "{{workflow.name}}")

    # --- Requirement: Launcher registers every workflow template --------------------
    # The launcher must register templates INTO the namespace the Workflow actually runs in,
    # and that value must be a literal: `argo submit -n <ns>` does not redirect a submission
    # (the manifest's metadata.namespace wins), so an env-var override could only publish the
    # templates into a different project than the one the Workflow lands in.
    launcher = (ROOT / "runai_run_pipeline.sh").read_text(encoding="utf-8")
    m = re.search(r"(?m)^NAMESPACE=(.*)$", launcher)
    check("launcher declares NAMESPACE", bool(m), True)
    if m:
        raw = m.group(1).strip()
        check(
            "launcher namespace matches the Workflow's metadata.namespace",
            raw.strip("\"'"),
            wf["metadata"]["namespace"],
        )
        check(
            "launcher namespace is a literal, not an env-var expansion",
            "$" in raw or "{" in raw,
            False,
        )
    check(
        "launcher registers every template the DAG references",
        sorted(re.findall(r"\"(sleap-roots-[a-z-]+-template)\.yaml\"", launcher)),
        sorted(f[:-5] for f in [GATE, *BATCH_STAGES.values()]),
    )

    # --- Reproducibility: pins ------------------------------------------------------
    images: dict[str, str] = {}
    for fname in [GATE, *BATCH_STAGES.values()]:
        images[fname] = load(fname)["spec"]["templates"][0]["container"]["image"]
    check(
        "no manifest pins :latest",
        [f for f, i in images.items() if i.endswith(":latest")],
        [],
    )
    # Every bloomctl reference must agree -- the gate reuses the image, so a half-done bump
    # would leave two stages on one build and the gate on another with nothing complaining.
    bloomctl = {i for i in images.values() if "bloomctl" in i}
    check("all bloomctl references are identical", len(bloomctl), 1)

    print()
    if _failures:
        print(f"=== {len(_failures)} FAILED, {_passes} passed ===")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"=== ALL {_passes} ASSERTIONS PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
