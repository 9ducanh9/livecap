"""Read-only benchmark guard. No app calls, secret output, apply or destroy."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TF_ROOT = ROOT / "infrastructure" / "benchmark"
ACCOUNT = "720459752315"
REGION = "ap-southeast-1"
KEY = "livecap/benchmark/terraform.tfstate"
BUCKET = f"livecap-terraform-state-dev-{ACCOUNT}"
FIELDS = {
    "environment", "aws_region", "expected_account_id", "owner", "shared_vpc_id",
    "shared_public_subnet_ids", "shared_private_subnet_ids", "image_git_sha",
    "benchmark_client_ipv4_cidrs", "monthly_budget_limit_usd", "log_retention_days",
    "max_sessions_per_ip",
    "benchmark_origin_hostname",
    "benchmark_alert_email",
}
RESOURCE_TYPES = {
    "terraform_data", "aws_ecr_repository", "aws_s3_bucket", "aws_s3_bucket_public_access_block",
    "aws_s3_bucket_server_side_encryption_configuration", "aws_s3_bucket_lifecycle_configuration",
    "aws_dynamodb_table", "aws_cognito_user_pool", "aws_cognito_user_pool_client",
    "aws_cognito_user_pool_domain", "aws_ssm_parameter", "aws_cloudwatch_log_group",
    "aws_iam_role", "aws_iam_role_policy", "aws_ecs_cluster", "aws_ecs_task_definition",
    "aws_ecs_service", "aws_appautoscaling_target", "aws_security_group", "aws_lb",
    "aws_lb_target_group", "aws_lb_listener", "aws_cloudfront_distribution",
    "aws_wafv2_ip_set", "aws_wafv2_web_acl", "aws_wafv2_web_acl_association",
    "aws_sns_topic", "aws_sns_topic_policy", "aws_budgets_budget",
    "aws_acm_certificate", "aws_acm_certificate_validation", "aws_sns_topic_subscription",
}
FORBIDDEN = re.compile(
    r"livecap-(?:target-(?:service|backend|alb|tg)-dev|preview-(?:service|backend|tg)-dev|"
    r"sessions-dev|usage-dev|transcripts-dev|transcript-history-dev|room-events-dev|"
    r"admin-audit-dev|ecs-task(?:-execution)?-dev|backend-dev)"
)
SECRET = re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


class GuardError(ValueError):
    """Safe, authored diagnostic; never include config values or CLI stderr."""


def command(args: list[str]) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        # CLI stderr can contain URLs or tokens. Never echo it.
        raise GuardError(f"{args[0]} command failed (exit {result.returncode}); inspect locally")
    return result.stdout


def validate_config(config: dict) -> None:
    if set(config) != FIELDS:
        raise GuardError("Use the exact benchmark JSON schema; unknown/missing keys are forbidden")
    if (config["environment"], config["aws_region"], config["expected_account_id"]) != ("benchmark", REGION, ACCOUNT):
        raise GuardError("Wrong benchmark environment/account/region")
    if not re.fullmatch(r"[0-9a-f]{40}", config["image_git_sha"]):
        raise GuardError("Full image Git SHA required")
    if not re.fullmatch(r"benchmark-origin\.[a-z0-9.-]+", config["benchmark_origin_hostname"]):
        raise GuardError("Only a new benchmark-origin hostname is permitted")
    if config["shared_vpc_id"] != "vpc-0d3a769b408f44be5":
        raise GuardError("Shared VPC differs from audited VPC; repeat network audit")
    for key, expected in {
        "shared_public_subnet_ids": {"subnet-0e7ac68941f5f6dbc", "subnet-05b93952bdbc666fb"},
        "shared_private_subnet_ids": {"subnet-0e6c54e39c800f12f", "subnet-0260e958f366bdfb5"},
    }.items():
        if len(config[key]) != 2 or set(config[key]) != expected:
            raise GuardError("Subnets differ from audited network")
    if not config["owner"].strip() or config["monthly_budget_limit_usd"] <= 0:
        raise GuardError("Owner and positive budget threshold required")
    if config["benchmark_alert_email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", config["benchmark_alert_email"]):
        raise GuardError("Invalid cost alert email")
    if config["log_retention_days"] not in {1, 3, 5, 7} or not 4 <= config["max_sessions_per_ip"] <= 16:
        raise GuardError("Invalid retention/per-IP cap")
    if not config["benchmark_client_ipv4_cidrs"]:
        raise GuardError("Explicit client allowlist required")
    for value in config["benchmark_client_ipv4_cidrs"]:
        network = ipaddress.ip_network(value)
        if network.version != 4 or network.prefixlen != 32:
            raise GuardError("Only IPv4 /32 clients allowed")
    if SECRET.search(json.dumps(config)):
        raise GuardError("Credential-like data found; do not print or continue")


def validate_backend(path: Path) -> None:
    if os.getenv("TF_WORKSPACE", "default") != "default":
        raise GuardError("Benchmark uses the default workspace and a dedicated key")
    selection = TF_ROOT / ".terraform" / "environment"
    if selection.exists() and selection.read_text().strip() != "default":
        raise GuardError("Non-default initialized workspace is forbidden")
    # Require exact, secret-free backend format; arbitrary overrides are rejected.
    content = path.read_text(encoding="utf-8")
    assignments = {}
    for line in content.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        key, separator, value = line.partition("=")
        if not separator or key.strip() in assignments:
            raise GuardError("Invalid/duplicate backend assignment")
        assignments[key.strip()] = json.loads(value.strip())
    expected = {"bucket": BUCKET, "key": KEY, "region": REGION, "encrypt": True,
                "use_lockfile": True, "allowed_account_ids": [ACCOUNT]}
    if assignments != expected:
        raise GuardError("Wrong backend selection or unsupported override")
    metadata = TF_ROOT / ".terraform" / "terraform.tfstate"
    if metadata.exists():
        backend = json.loads(metadata.read_text(encoding="utf-8"))["backend"]
        if backend["type"] != "s3" or any(backend["config"].get(k) != v for k, v in expected.items()):
            raise GuardError("Initialized backend differs from reviewed benchmark backend")


def validate_plan(plan: dict, config: dict, *, destroy: bool = False, scope: str = "full") -> dict:
    if SECRET.search(json.dumps(plan)):
        raise GuardError("Credential-like value in plan; stop without printing")
    variables = {k: v["value"] for k, v in plan.get("variables", {}).items()}
    if variables != config:
        raise GuardError("Plan variables differ from selected benchmark var-file")
    if plan.get("errored") or (plan.get("complete") is False and scope != "bootstrap"):
        raise GuardError("Incomplete or errored plan")
    counts = {"create": 0, "update": 0, "delete": 0, "production_create": 0,
              "production_update": 0, "production_delete": 0}
    resources = []
    for change in plan.get("resource_changes", []):
        if change.get("mode") == "data":
            continue
        address = change["address"]
        if scope == "bootstrap" and address not in {"aws_ecr_repository.benchmark", "aws_acm_certificate.benchmark"}:
            raise GuardError("Bootstrap may manage only isolated ECR and ACM certificate")
        if change["type"] not in RESOURCE_TYPES or not re.fullmatch(r"(?:terraform_data|aws_[a-z0-9_]+)\.benchmark[a-z_]*(?:\[[^\]]+\])?", address):
            raise GuardError("Unexpected managed resource in benchmark plan")
        actions = change["change"]["actions"]
        allowed = {"no-op", "delete"} if destroy else {"no-op", "create"}
        if not set(actions) <= allowed:
            raise GuardError("Unexpected update/delete/replace: stop before apply")
        payload = json.dumps(change["change"])
        if FORBIDDEN.search(payload) or SECRET.search(payload):
            raise GuardError("Production reference or credential-like value: stop")
        values = change["change"].get("before" if destroy else "after") or {}
        for field in ("name", "bucket", "family", "comment"):
            if field in values and values[field] is not None and not (
                str(values[field]).startswith("livecap-benchmark")
                or str(values[field]).startswith("/ecs/livecap-benchmark")
                or str(values[field]).startswith("/livecap/benchmark/")
            ):
                raise GuardError("Managed resource name is outside benchmark namespace")
        for action in actions:
            if action in counts:
                counts[action] += 1
        if actions != ["no-op"]:
            resources.append({"address": address, "actions": actions})
    return {"counts": counts, "resources": resources}


def image_and_certificate_ready(config: dict, profile: str) -> dict:
    """Read-only, pre-service checks. Does not claim source/image equivalence."""
    common = ["--profile", profile, "--region", REGION, "--output", "json", "--no-cli-pager"]
    repository = json.loads(command(["aws", "ecr", "describe-repositories", "--repository-names",
                                     "livecap-benchmark-backend", *common]))["repositories"][0]
    if repository["registryId"] != ACCOUNT or repository["imageTagMutability"] != "IMMUTABLE":
        raise GuardError("Wrong registry or mutable image tags")
    image = json.loads(command(["aws", "ecr", "describe-images", "--repository-name", "livecap-benchmark-backend",
                               "--image-ids", "imageTag=" + config["image_git_sha"] + "-amd64", *common]))["imageDetails"][0]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image["imageDigest"]):
        raise GuardError("Missing image digest")
    certificates = json.loads(command(["aws", "acm", "list-certificates", "--certificate-statuses", "ISSUED", *common]))
    matching = [c for c in certificates["CertificateSummaryList"]
                if c["DomainName"] == config["benchmark_origin_hostname"]]
    if len(matching) != 1:
        raise GuardError("Require exactly one issued benchmark certificate")
    certificate = json.loads(command(["aws", "acm", "describe-certificate", "--certificate-arn",
                                       matching[0]["CertificateArn"], *common]))["Certificate"]
    if certificate["Status"] != "ISSUED" or certificate["SubjectAlternativeNames"] != [config["benchmark_origin_hostname"]]:
        raise GuardError("Certificate scope/status differs from benchmark origin")
    return {"image_digest": image["imageDigest"], "certificate_arn": certificate["CertificateArn"],
            "manual_gates_remaining": ["source/build provenance and Linux amd64/Python runtime",
                                        "DNS ownership, cost approval, plan review and P4B authorization",
                                        "after provisioning: exact origin CNAME, alert delivery, auth/quota smoke"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--var-file", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--profile", default="camgiacntn")
    parser.add_argument("--mode", choices=["design", "release"], default="release")
    parser.add_argument("--scope", choices=["full", "bootstrap"], default="full")
    parser.add_argument("--plan-json", type=Path)
    parser.add_argument("--destroy-plan", action="store_true")
    args = parser.parse_args()
    if args.destroy_plan and args.scope != "full":
        raise GuardError("Destroy must review the complete benchmark graph")
    config = json.loads(args.var_file.read_text(encoding="utf-8"))
    validate_config(config)
    validate_backend(args.backend_config)
    identity = json.loads(command(["aws", "sts", "get-caller-identity", "--profile", args.profile,
                                   "--region", REGION, "--output", "json", "--no-cli-pager"]))
    if identity["Account"] != ACCOUNT:
        raise GuardError("Wrong caller account")
    print(json.dumps({"caller": {k: identity[k] for k in ("Account", "Arn")}, "region": REGION,
                      "backend_key": KEY, "mode": args.mode}, indent=2))
    sha = command(["git", "rev-parse", "HEAD"]).strip()
    dirty = bool(command(["git", "status", "--porcelain"]).strip())
    print(json.dumps({"git_sha": sha, "clean_worktree": not dirty,
                      "image_tag": config["image_git_sha"] + "-amd64"}))
    if sha != config["image_git_sha"]:
        raise GuardError("HEAD differs from image source checkpoint")
    if args.plan_json:
        print(json.dumps(validate_plan(json.loads(args.plan_json.read_text(encoding="utf-8")), config,
                                       destroy=args.destroy_plan, scope=args.scope), indent=2))
    if args.mode == "release":
        if dirty:
            raise GuardError("Release requires a clean worktree; design allows reviewable P4A edits only")
        if not args.destroy_plan and any(not ipaddress.ip_network(c).network_address.is_global for c in config["benchmark_client_ipv4_cidrs"]):
            raise GuardError("Replace fail-closed placeholder with real benchmark public /32")
        if not args.plan_json:
            raise GuardError("Release requires a reviewed saved plan")
        if not args.destroy_plan and not config["benchmark_alert_email"]:
            raise GuardError("Cost alert recipient must be configured before release")
        if args.scope == "full" and not args.destroy_plan:
            print(json.dumps(image_and_certificate_ready(config, args.profile), indent=2))
        print("LOCAL/PLAN release checks passed; complete the documented manual gates. This is not apply approval.")
    else:
        print("DESIGN checks only; this is not deploy approval or performance evidence")


if __name__ == "__main__":
    try:
        main()
    except GuardError as error:
        raise SystemExit(f"Benchmark preflight FAILED: {error}. No app mutation performed.")
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
        # Do not accidentally print a token/secret from a malformed config or CLI response.
        raise SystemExit("Benchmark preflight FAILED. Inspect inputs locally; no app mutation was performed.")
