"""Deterministic runtime profiles, configuration assembly, and package compatibility."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class RuntimeConfigError(ValueError):
    """Raised when runtime configuration is unsafe or internally inconsistent."""


PROFILE_KINDS = {"local", "team", "hosted", "production"}
COMPONENTS = {
    "liaison", "project_lead", "scheduler", "worker", "state", "artifacts",
    "credential_broker", "telemetry",
}
SECRET_TERMS = {"password", "secret", "token", "api_key", "apikey", "credential"}
SECRET_REFERENCE_PREFIXES = ("env://", "file://", "broker://")
PROTECTED_PATHS = {
    "security.allowRawSecrets",
    "security.verifyProvenance",
    "state.authority",
    "state.snapshotAuthority",
}


@dataclass(frozen=True)
class RuntimeAssembly:
    profile_id: str
    profile_kind: str
    configuration: dict[str, Any]
    digest: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class CompatibilityResult:
    compatible: bool
    reasons: tuple[str, ...]


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise RuntimeConfigError(f"{key} must be a non-empty string")
    return result


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _walk(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            yield path, child
            yield from _walk(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{prefix}[{index}]")


def _contains_secret_name(path: str) -> bool:
    normalized = path.lower().replace("-", "_")
    return any(term in normalized for term in SECRET_TERMS)


def validate_runtime_profile(profile: dict[str, Any]) -> None:
    for key in ("schemaVersion", "profileId", "profileKind", "description"):
        _required_string(profile, key)
    if profile["profileKind"] not in PROFILE_KINDS:
        raise RuntimeConfigError("profileKind is invalid")
    components = profile.get("components")
    if not isinstance(components, list) or not components:
        raise RuntimeConfigError("components must be a non-empty array")
    if any(component not in COMPONENTS for component in components):
        raise RuntimeConfigError("components contains an unknown component")
    if len(components) != len(set(components)):
        raise RuntimeConfigError("components contains duplicates")
    configuration = profile.get("configuration")
    if not isinstance(configuration, dict):
        raise RuntimeConfigError("configuration must be an object")
    state = configuration.get("state")
    if not isinstance(state, dict) or state.get("authority") != "state.db":
        raise RuntimeConfigError("state.authority must be state.db")
    if state.get("snapshotAuthority") is not False:
        raise RuntimeConfigError("state.snapshotAuthority must be false")
    security = configuration.get("security")
    if not isinstance(security, dict) or security.get("allowRawSecrets") is not False:
        raise RuntimeConfigError("security.allowRawSecrets must be false")
    if profile["profileKind"] == "production":
        required = set(COMPONENTS)
        missing = sorted(required - set(components))
        if missing:
            raise RuntimeConfigError(f"production profile is missing components: {missing}")
        if security.get("verifyProvenance") is not True:
            raise RuntimeConfigError("production must verify provenance")
        if configuration.get("telemetry", {}).get("enabled") is not True:
            raise RuntimeConfigError("production telemetry must be enabled")
        if configuration.get("recovery", {}).get("restoreTestsRequired") is not True:
            raise RuntimeConfigError("production restore tests must be required")
    for path, value in _walk(configuration):
        if _contains_secret_name(path) and value is not None:
            if not isinstance(value, str) or not value.startswith(SECRET_REFERENCE_PREFIXES):
                if path not in {"security.allowRawSecrets"}:
                    raise RuntimeConfigError(f"{path} must contain a secret reference, not a value")


def _merge(base: dict[str, Any], override: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result = copy.deepcopy(base)
    for supplied_key, value in override.items():
        matches = [key for key in result if key.lower() == supplied_key.lower()]
        key = matches[0] if len(matches) == 1 else supplied_key
        path = f"{prefix}.{key}" if prefix else key
        if path in PROTECTED_PATHS and key in result and result[key] != value:
            raise RuntimeConfigError(f"protected configuration cannot be overridden: {path}")
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value, path)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _parse_env_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def environment_overrides(environment: Mapping[str, str], prefix: str = "V3__") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in sorted(environment):
        if not name.startswith(prefix):
            continue
        parts = [part.lower() for part in name[len(prefix):].split("__") if part]
        if not parts:
            raise RuntimeConfigError(f"invalid environment override: {name}")
        cursor = result
        for part in parts[:-1]:
            existing = cursor.setdefault(part, {})
            if not isinstance(existing, dict):
                raise RuntimeConfigError(f"conflicting environment override: {name}")
            cursor = existing
        cursor[parts[-1]] = _parse_env_value(environment[name])
    return result


def assemble_runtime(
    profile: dict[str, Any],
    *,
    defaults: dict[str, Any] | None = None,
    project: dict[str, Any] | None = None,
    environment: Mapping[str, str] | None = None,
    command_line: dict[str, Any] | None = None,
) -> RuntimeAssembly:
    validate_runtime_profile(profile)
    configuration: dict[str, Any] = {}
    sources = []
    for label, layer in (
        ("defaults", defaults or {}),
        ("profile", profile["configuration"]),
        ("project", project or {}),
        ("environment", environment_overrides(environment or {})),
        ("command_line", command_line or {}),
    ):
        if layer:
            if not isinstance(layer, dict):
                raise RuntimeConfigError(f"{label} configuration must be an object")
            configuration = _merge(configuration, layer)
            sources.append(label)
    assembled = {**profile, "configuration": configuration}
    validate_runtime_profile(assembled)
    return RuntimeAssembly(
        profile["profileId"], profile["profileKind"], configuration,
        _stable_digest(configuration), tuple(sources),
    )


def validate_package_manifest(manifest: dict[str, Any]) -> None:
    for key in ("schemaVersion", "packageName", "packageVersion", "frameworkVersion", "pythonRequires"):
        _required_string(manifest, key)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RuntimeConfigError("artifacts must be a non-empty array")
    paths = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise RuntimeConfigError("artifact must be an object")
        path = _required_string(artifact, "path")
        digest = _required_string(artifact, "sha256")
        if path.startswith("/") or ".." in Path(path).parts:
            raise RuntimeConfigError("artifact path must remain inside the package")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise RuntimeConfigError("artifact sha256 is invalid")
        if path in paths:
            raise RuntimeConfigError("artifact paths must be unique")
        paths.add(path)


def check_compatibility(
    manifest: dict[str, Any], *, framework_version: str, schema_version: str,
    supported_profile_kinds: set[str],
) -> CompatibilityResult:
    validate_package_manifest(manifest)
    reasons = []
    if manifest["frameworkVersion"] != framework_version:
        reasons.append("framework version does not match")
    if schema_version not in manifest.get("supportedSchemaVersions", []):
        reasons.append("state schema version is not supported")
    unsupported = set(manifest.get("supportedProfileKinds", [])) - PROFILE_KINDS
    if unsupported:
        reasons.append("manifest declares unknown profile kinds")
    if not supported_profile_kinds.intersection(manifest.get("supportedProfileKinds", [])):
        reasons.append("no compatible runtime profile kind is available")
    return CompatibilityResult(not reasons, tuple(reasons))
