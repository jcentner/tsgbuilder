"""
Centralized version and project metadata.

This is the single source of truth for version information used throughout TSG Builder.
Update APP_VERSION here when releasing a new version.

See docs/releasing.md for the release process.
"""

import os

# Application version - update this for each release
# Format: MAJOR.MINOR.PATCH (semver)
APP_VERSION = "1.0.2"

# Project URLs
GITHUB_URL = "https://github.com/jcentner/tsgbuilder"

# Signature appended to generated TSGs for usage tracking
# This makes TSGs searchable in the ADO wiki
TSG_SIGNATURE = f"\n\n---\n*Drafted with [TSG Builder]({GITHUB_URL}) v{APP_VERSION}*"

# Azure AI Language endpoint for PII detection (centralized, author-owned resource).
# Hardcoded default; silently overridable via LANGUAGE_ENDPOINT env var as an
# undocumented escape hatch for emergencies (not surfaced in UI, setup, or docs).
LANGUAGE_ENDPOINT = os.getenv(
    "LANGUAGE_ENDPOINT",
    "https://tsgbuilder-pii-language.cognitiveservices.azure.com/",
)
