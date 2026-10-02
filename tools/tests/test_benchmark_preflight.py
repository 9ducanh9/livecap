"""Safety checks against wrong state selection and production mutations."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("benchmark_preflight", ROOT / "tools/benchmark_preflight.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
CONFIG = json.loads((ROOT / "infrastructure/benchmark/benchmark.tfvars.json.example").read_text())


class BenchmarkSafetyTests(unittest.TestCase):
    def plan(self, address="aws_ecs_service.benchmark", actions=None, after=None):
        return {"variables": {k: {"value": v} for k, v in CONFIG.items()}, "complete": True,
                "resource_changes": [{"address": address, "mode": "managed", "type": "aws_ecs_service",
                                      "change": {"actions": actions or ["create"], "after": after or {"name": "livecap-benchmark-service"}}}]}

    def test_wrong_account_region_environment_rejected(self):
        for key, value in [("environment", "dev"), ("aws_region", "us-east-1"),
                           ("expected_account_id", "123456789012"), ("access_token", "test")]:
            config = copy.deepcopy(CONFIG)
            config[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                guard.validate_config(config)

    def test_open_allowlist_rejected(self):
        config = copy.deepcopy(CONFIG)
        config["benchmark_client_ipv4_cidrs"] = ["0.0.0.0/0"]
        with self.assertRaises(ValueError):
            guard.validate_config(config)

    def test_invalid_recipient_rejected_without_echoing_it(self):
        for email in ("yes", "someone@", "a\n@b.example"):
            config = copy.deepcopy(CONFIG)
            config["benchmark_alert_email"] = email
            with self.subTest(case=email), self.assertRaises(ValueError):
                guard.validate_config(config)

    def test_production_state_rejected(self):
        content = (ROOT / "infrastructure/benchmark/backend.hcl.example").read_text()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "backend.hcl"
            path.write_text(content.replace(guard.KEY, "livecap/main/terraform.tfstate"))
            with self.assertRaises(ValueError):
                guard.validate_backend(path)

    def test_managed_shared_resource_rejected(self):
        with self.assertRaises(ValueError):
            guard.validate_plan(self.plan(address="aws_ecs_service.target_backend"), CONFIG)

    def test_workspace_cannot_redirect_state(self):
        with patch.dict(guard.os.environ, {"TF_WORKSPACE": "production"}), self.assertRaises(ValueError):
            guard.validate_backend(ROOT / "infrastructure/benchmark/backend.hcl.example")

    def test_output_credential_is_rejected(self):
        plan = self.plan()
        # Shape-only dummy string for a privacy regression, not an AWS credential.
        plan["output_changes"] = {"unsafe": {"after": "ASIA" + "Z" * 16}}
        with self.assertRaises(ValueError):
            guard.validate_plan(plan, CONFIG)

    def test_update_delete_and_replace_rejected(self):
        for actions in [["update"], ["delete"], ["delete", "create"]]:
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                guard.validate_plan(self.plan(actions=actions), CONFIG)

    def test_production_application_reference_rejected(self):
        with self.assertRaises(ValueError):
            guard.validate_plan(self.plan(after={"environment": "livecap-usage-dev"}), CONFIG)

    def test_plan_variables_cannot_drift(self):
        plan = self.plan()
        plan["variables"]["environment"]["value"] = "dev"
        with self.assertRaises(ValueError):
            guard.validate_plan(plan, CONFIG)

    def test_counts_from_safe_plan(self):
        result = guard.validate_plan(self.plan(), CONFIG)
        self.assertEqual(result["counts"]["create"], 1)
        self.assertEqual(result["counts"]["production_update"], 0)

    def test_benchmark_address_cannot_hide_nonbenchmark_name(self):
        with self.assertRaises(ValueError):
            guard.validate_plan(self.plan(after={"name": "some-production-service"}), CONFIG)

    def test_bootstrap_cannot_include_service(self):
        with self.assertRaises(ValueError):
            guard.validate_plan(self.plan(), CONFIG, scope="bootstrap")

    def test_targeted_bootstrap_accepts_only_ecr_and_certificate(self):
        plan = self.plan()
        plan["complete"] = False  # Targeting cannot certify the omitted graph.
        plan["resource_changes"][0].update(address="aws_ecr_repository.benchmark", type="aws_ecr_repository")
        plan["resource_changes"][0]["change"]["after"] = {"name": "livecap-benchmark-backend"}
        self.assertEqual(guard.validate_plan(plan, CONFIG, scope="bootstrap")["counts"]["create"], 1)
        with self.assertRaises(ValueError):
            guard.validate_plan(plan, CONFIG)

    def test_full_release_rejects_mutable_repository(self):
        with patch.object(guard, "command", return_value=json.dumps({"repositories": [
                {"registryId": guard.ACCOUNT, "imageTagMutability": "MUTABLE"}]})), self.assertRaises(ValueError):
            guard.image_and_certificate_ready(CONFIG, "camgiacntn")

    def test_full_release_rejects_missing_issued_certificate(self):
        responses = [json.dumps({"repositories": [{"registryId": guard.ACCOUNT, "imageTagMutability": "IMMUTABLE"}]}),
                     json.dumps({"imageDetails": [{"imageDigest": "sha256:" + "a" * 64}]}),
                     json.dumps({"CertificateSummaryList": []})]
        with patch.object(guard, "command", side_effect=responses), self.assertRaises(ValueError):
            guard.image_and_certificate_ready(CONFIG, "camgiacntn")

    def test_destroy_only_benchmark(self):
        result = guard.validate_plan(self.plan(actions=["delete"]), CONFIG, destroy=True)
        self.assertEqual(result["counts"]["delete"], 1)


if __name__ == "__main__":
    unittest.main()
