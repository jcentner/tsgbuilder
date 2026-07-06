"""Tests for release workflow and packaging contracts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


WORKFLOW_PATH = Path(".github/workflows/build.yml")
RELEASING_DOC_PATH = Path("docs/releasing.md")


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.mark.unit
def test_workflow_reads_app_version_from_version_py():
    workflow = _workflow_text()

    assert "from version import APP_VERSION" in workflow
    assert "app_version=$(python" in workflow
    assert "version=$app_version" in workflow
    assert "/DAppVersion=${{ steps.app_version.outputs.version }}" in workflow
    assert "/DAppVersion=${{ github.ref_name }}" not in workflow
    assert '"${{ github.ref_name }}" -replace' not in workflow


@pytest.mark.unit
def test_workflow_release_uses_app_version_tag_and_name():
    workflow = _workflow_text()

    assert "tag_name: v${{ steps.app_version.outputs.version }}" in workflow
    assert "name: TSG Builder v${{ steps.app_version.outputs.version }}" in workflow
    assert "## TSG Builder v${{ steps.app_version.outputs.version }}" in workflow
    assert "## TSG Builder ${{ github.ref_name }}" not in workflow


@pytest.mark.unit
def test_manual_release_requires_main_branch():
    workflow = _workflow_text()

    assert "Validate manual release branch" in workflow
    assert "inputs.create_release && github.ref != 'refs/heads/main'" in workflow
    assert "Manual draft releases must be run from the main branch" in workflow


@pytest.mark.unit
def test_workflow_release_files_match_contract():
    workflow = _workflow_text()
    match = re.search(r"files:\s*\|\n(?P<files>(?:\s+release/[^\n]+\n)+)", workflow)

    assert match is not None
    files = [line.strip().removeprefix("release/") for line in match.group("files").splitlines() if line.strip()]
    assert files == [
        "tsg-builder-linux.zip",
        "tsg-builder-macos.zip",
        "tsg-builder-windows.zip",
        "tsg-builder-windows-setup.zip",
        "SHA256SUMS.txt",
    ]


@pytest.mark.unit
def test_releasing_docs_describe_manual_release_version_source():
    docs = RELEASING_DOC_PATH.read_text(encoding="utf-8")

    assert "Manual dispatch, `create_release=false`" in docs
    assert "Manual dispatch, `create_release=true`" in docs
    assert "select the `main` branch" in docs
    assert "created as `v{APP_VERSION}`" in docs
