"""Delivery-path checks for the release -> deploy workflow pair.

Locked-down defect: deploy.yml resolved the release asset with
``gh release view --json assets --jq '.assets[0].browser_download_url'``, a field
``gh`` never exposes (its asset projection is apiUrl, contentType, createdAt,
digest, downloadCount, id, label, name, size, state, updatedAt, url), so a
dispatched deploy failed with "release <tag> has no asset to deploy" even though
the release carried its zip.

The second locked-down defect: release.yml publishes the release with the
repository ``GITHUB_TOKEN``, and GitHub does not cascade workflow runs for events
produced with that token, so ``on: release: types: [published]`` never enqueued
this workflow. release.yml has to dispatch it explicitly.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess

BASH = shutil.which("bash") or "bash"

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy-release.sh"
ASSETS_FIXTURE = ROOT / "tests" / "fixtures" / "gh-release-assets.json"
STEP_NAME = "- name: Resolve the release tag and its asset"


def _without_comments(path):
    """Workflow text with YAML comment lines dropped."""
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def _dedent(lines):
    indents = [len(line) - len(line.lstrip(" ")) for line in lines if line.strip()]
    cut = min(indents) if indents else 0
    return "\n".join(line[cut:] if line.strip() else "" for line in lines) + "\n"


def resolver_script():
    """The resolver step's run script, taken verbatim from deploy.yml."""
    lines = DEPLOY.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.strip() == STEP_NAME)
    body = []
    for line in lines[start + 1 :]:
        if line.lstrip().startswith("- name: "):
            break
        body.append(line)
    marker = next(index for index, line in enumerate(body) if line.strip() == "run: |")
    return _dedent(body[marker + 1 :])


def resolver_jq():
    match = re.search(r"--jq '([^']+)'", resolver_script())
    assert match, "the resolver no longer passes a jq expression to gh"
    return match.group(1)


def run_resolver(tmp_path, gh_body, event_tag, input_tag):
    """Run the resolver the way the workflow does: bash -e, gh from PATH."""
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir(parents=True, exist_ok=True)
    gh.write_text("#!/usr/bin/env bash\n" + gh_body + "\n", encoding="utf-8")
    gh.chmod(0o755)
    script = tmp_path / "resolver.sh"
    script.write_text(resolver_script(), encoding="utf-8")
    env_file = tmp_path / "github_env"
    env_file.write_text("", encoding="utf-8")
    env = {
        "PATH": os.pathsep.join(
            [str(gh.parent), os.environ.get("PATH", "/usr/bin:/bin")]
        ),
        "GITHUB_ENV": str(env_file),
        "GITHUB_REPOSITORY": "owner/repo",
        "EVENT_TAG": event_tag,
        "INPUT_TAG": input_tag,
    }
    result = subprocess.run(
        [BASH, "-e", str(script)], env=env, capture_output=True, text=True
    )
    return result, env_file.read_text(encoding="utf-8")


ASSET = "https://github.com/owner/repo/releases/download/v1.1.1/to-do-list-api-v1.1.1.zip"
# A gh stub that prints the asset URL the resolver is expected to export.
GH_PRINT_URL = 'printf "%s\n" "' + ASSET + '"'


def test_resolver_jq_expression_selects_the_uploaded_asset_url():
    expression = resolver_jq()
    assert "browser_download_url" not in expression
    assert 'state == "uploaded"' in expression
    jq = shutil.which("jq")
    if jq is None:
        return  # exercised on the runner, which ships jq
    result = subprocess.run(
        [jq, "-r", expression, str(ASSETS_FIXTURE)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    expected = json.loads(ASSETS_FIXTURE.read_text(encoding="utf-8"))["assets"][0]["url"]
    assert result.stdout.strip() == expected


def test_resolver_exports_the_asset_url_for_the_dispatch_path(tmp_path):
    result, env_file = run_resolver(tmp_path, GH_PRINT_URL, "", "v1.1.1")
    assert result.returncode == 0, result.stderr
    assert "RELEASE_TAG=v1.1.1" in env_file
    assert "ASSET_URL=" + ASSET in env_file


def test_resolver_exports_the_asset_url_for_the_release_event_path(tmp_path):
    result, env_file = run_resolver(tmp_path, GH_PRINT_URL, "v1.1.1", "")
    assert result.returncode == 0, result.stderr
    assert "RELEASE_TAG=v1.1.1" in env_file
    assert "ASSET_URL=" + ASSET in env_file


def test_resolver_fails_loudly_when_no_asset_is_uploaded(tmp_path):
    result, env_file = run_resolver(tmp_path, 'printf "\n"', "v1.1.1", "")
    assert result.returncode != 0
    assert "release v1.1.1 has no asset to deploy" in result.stderr
    assert "ASSET_URL" not in env_file


def test_resolver_fails_loudly_when_the_release_is_missing(tmp_path):
    result, env_file = run_resolver(
        tmp_path, 'echo "release not found" >&2; exit 1', "v9.9.9", ""
    )
    assert result.returncode != 0
    assert "ASSET_URL" not in env_file


def test_resolver_requires_a_tag_on_either_path(tmp_path):
    result, env_file = run_resolver(tmp_path, GH_PRINT_URL, "", "")
    assert result.returncode != 0
    assert "ASSET_URL" not in env_file


def test_deploy_script_rejects_an_empty_or_foreign_asset_url():
    for url in ("", "http://evil.example/to-do-list-api-v1.1.1.zip"):
        result = subprocess.run(
            [BASH, str(DEPLOY_SCRIPT), "v1.1.1", url], capture_output=True, text=True
        )
        assert result.returncode == 64, (url, result.stdout, result.stderr)
        assert "Unexpected release asset URL" in result.stderr
    result = subprocess.run(
        [BASH, str(DEPLOY_SCRIPT), "1.1.1", ASSET], capture_output=True, text=True
    )
    assert result.returncode == 64
    assert "Unexpected release tag" in result.stderr


def test_deploy_workflow_declares_both_trigger_paths():
    body = _without_comments(DEPLOY)
    assert re.search("^ {2}release:$", body, re.M)
    assert re.search(r"^ {4}types: \[published\]$", body, re.M)
    assert re.search("^ {2}workflow_dispatch:$", body, re.M)
    assert re.search("^ {4}inputs:$", body, re.M)
    assert re.search("^ {6}release_tag:$", body, re.M)
    assert re.search("^ {8}required: true$", body, re.M)
    assert "github.event.release.tag_name" in body
    assert "inputs.release_tag" in body
    assert "github.event.release.assets" not in body


def test_release_workflow_requests_the_deploy_run():
    body = _without_comments(RELEASE)
    assert re.search("^ {2}actions: write$", body, re.M)
    assert "gh workflow run deploy.yml" in body
    assert "--ref" in body and "github.event.repository.default_branch" in body
    assert "-f release_tag=" in body
