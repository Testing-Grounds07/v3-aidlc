import unittest

from v3_aidlc.runtime_config import (
    RuntimeConfigError, assemble_runtime, check_compatibility,
    environment_overrides, validate_package_manifest, validate_runtime_profile,
)


def profile(kind="local"):
    components = ["liaison", "project_lead", "scheduler", "worker", "state", "artifacts"]
    if kind == "production":
        components += ["credential_broker", "telemetry"]
    return {
        "schemaVersion": "0.1", "profileId": f"PROFILE-{kind.upper()}",
        "profileKind": kind, "description": f"{kind} runtime", "components": components,
        "configuration": {
            "state": {"authority": "state.db", "snapshotAuthority": False},
            "security": {"allowRawSecrets": False, "verifyProvenance": kind == "production"},
            "telemetry": {"enabled": kind == "production"},
            "recovery": {"restoreTestsRequired": kind == "production"},
            "scheduler": {"maxConcurrency": 1},
        },
    }


class RuntimeConfigTest(unittest.TestCase):
    def test_validates_local_profile(self):
        validate_runtime_profile(profile())

    def test_production_requires_all_components(self):
        value = profile("production")
        value["components"].remove("telemetry")
        with self.assertRaisesRegex(RuntimeConfigError, "missing components"):
            validate_runtime_profile(value)

    def test_production_requires_provenance(self):
        value = profile("production")
        value["configuration"]["security"]["verifyProvenance"] = False
        with self.assertRaisesRegex(RuntimeConfigError, "verify provenance"):
            validate_runtime_profile(value)

    def test_rejects_raw_secret(self):
        value = profile()
        value["configuration"]["provider"] = {"apiKey": "actual-secret"}
        with self.assertRaisesRegex(RuntimeConfigError, "secret reference"):
            validate_runtime_profile(value)

    def test_accepts_secret_reference(self):
        value = profile()
        value["configuration"]["provider"] = {"apiKey": "broker://providers/main"}
        validate_runtime_profile(value)

    def test_precedence_is_deterministic(self):
        result = assemble_runtime(
            profile(), defaults={"scheduler": {"maxConcurrency": 2, "queue": "fifo"}},
            project={"scheduler": {"maxConcurrency": 3}},
            environment={"V3__SCHEDULER__MAXCONCURRENCY": "4"},
            command_line={"scheduler": {"maxconcurrency": 5}},
        )
        self.assertEqual(result.configuration["scheduler"]["maxConcurrency"], 5)
        self.assertEqual(result.sources, ("defaults", "profile", "project", "environment", "command_line"))

    def test_protected_state_authority_cannot_change(self):
        with self.assertRaisesRegex(RuntimeConfigError, "protected"):
            assemble_runtime(profile(), project={"state": {"authority": "snapshot.json"}})

    def test_environment_values_are_typed(self):
        value = environment_overrides({
            "V3__TELEMETRY__ENABLED": "true", "V3__SCHEDULER__LIMIT": "4",
            "IGNORED": "x",
        })
        self.assertEqual(value, {"scheduler": {"limit": 4}, "telemetry": {"enabled": True}})

    def test_assembly_digest_is_stable(self):
        first = assemble_runtime(profile(), project={"x": {"a": 1, "b": 2}})
        second = assemble_runtime(profile(), project={"x": {"b": 2, "a": 1}})
        self.assertEqual(first.digest, second.digest)

    def test_manifest_validation(self):
        validate_package_manifest(self.manifest())

    def test_manifest_rejects_escape_path(self):
        value = self.manifest()
        value["artifacts"][0]["path"] = "../escape"
        with self.assertRaisesRegex(RuntimeConfigError, "inside"):
            validate_package_manifest(value)

    def test_compatibility_reports_mismatch(self):
        result = check_compatibility(
            self.manifest(), framework_version="9.0", schema_version="0.1",
            supported_profile_kinds={"local"},
        )
        self.assertFalse(result.compatible)
        self.assertIn("framework version does not match", result.reasons)

    @staticmethod
    def manifest():
        return {
            "schemaVersion": "0.1", "packageName": "v3-aidlc", "packageVersion": "0.1.0",
            "frameworkVersion": "0.1.0", "pythonRequires": ">=3.11",
            "supportedSchemaVersions": ["0.1"],
            "supportedProfileKinds": ["local", "production"],
            "artifacts": [{"path": "src/v3_aidlc/__init__.py", "sha256": "a" * 64}],
        }


if __name__ == "__main__":
    unittest.main()
