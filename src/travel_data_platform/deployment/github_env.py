"""Sync GitHub Environment secrets and variables from a declarative config.

Ported from the `setup-github-env` tooling used in Cyberk projects. The config file
(TOML) declares which keys each workflow needs; values live in a gitignored
`.env.github.<stage>` file next to it and are pushed with the `gh` CLI.
"""

import base64
import json
import re
import secrets
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

ENV_FILE_PREFIX = ".env.github."
_REPO_SLUG_PATTERN = re.compile(r"[:/](?P<slug>[^/:]+/[^/]+?)(?:\.git)?/?$")


class GithubEnvSetupError(Exception):
    """Raised when the config, the provided values, or the gh CLI state is invalid."""


@dataclass(frozen=True)
class ValueDef:
    description: str | None = None
    optional: bool = False
    generate: bool = False
    pattern: str | None = None


@dataclass(frozen=True)
class EnvironmentDef:
    branch: str | None = None


@dataclass(frozen=True)
class GithubEnvConfig:
    environments: dict[str, EnvironmentDef]
    secrets: dict[str, ValueDef]
    variables: dict[str, ValueDef]

    def all_keys(self) -> list[str]:
        return [*self.secrets, *self.variables]

    def resolve_stages(self, stage: str) -> list[str]:
        if stage == "all":
            return list(self.environments)
        if stage not in self.environments:
            available = ", ".join(self.environments)
            raise GithubEnvSetupError(f'Unknown stage "{stage}". Available: {available}, all')
        return [stage]


@dataclass
class SetupResult:
    secrets_set: list[str] = field(default_factory=list)
    secrets_skipped: list[str] = field(default_factory=list)
    variables_set: list[str] = field(default_factory=list)
    variables_skipped: list[str] = field(default_factory=list)


class GhClient(Protocol):
    def ensure_environment(self, repo: str, env: str, branch: str | None) -> None: ...

    def list_secret_names(self, repo: str, env: str) -> set[str]: ...

    def list_variables(self, repo: str, env: str) -> dict[str, str]: ...

    def set_secret(self, repo: str, env: str, name: str, value: str) -> None: ...

    def set_variable(self, repo: str, env: str, name: str, value: str) -> None: ...


class SetupUI(Protocol):
    def info(self, message: str) -> None: ...

    def success(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def prompt_value(self, name: str, definition: ValueDef, stage: str, secret: bool) -> str: ...

    def confirm_overwrite(self, existing_names: list[str]) -> list[str]: ...


# ─── Config ──────────────────────────────────────────────────────────────────


def parse_config(text: str) -> GithubEnvConfig:
    raw = tomllib.loads(text)

    environments = {
        name: EnvironmentDef(branch=body.get("branch"))
        for name, body in raw.get("environments", {}).items()
    }
    if not environments:
        raise GithubEnvSetupError("Config must declare at least one [environments.<name>]")

    secret_defs = {
        name: _parse_value_def(name, body) for name, body in raw.get("secrets", {}).items()
    }
    variable_defs = {
        name: _parse_value_def(name, body) for name, body in raw.get("variables", {}).items()
    }

    generated_variables = [name for name, d in variable_defs.items() if d.generate]
    if generated_variables:
        raise GithubEnvSetupError(
            f"`generate` is only supported for secrets, not variables: {generated_variables}"
        )

    duplicated = sorted(set(secret_defs) & set(variable_defs))
    if duplicated:
        raise GithubEnvSetupError(f"Keys declared as both secret and variable: {duplicated}")

    return GithubEnvConfig(
        environments=environments,
        secrets=secret_defs,
        variables=variable_defs,
    )


def load_config(path: Path) -> GithubEnvConfig:
    return parse_config(path.read_text(encoding="utf-8"))


def _parse_value_def(name: str, body: Mapping[str, object]) -> ValueDef:
    allowed = {"description", "optional", "generate", "pattern"}
    unknown = set(body) - allowed
    if unknown:
        raise GithubEnvSetupError(f"Unknown option(s) for {name}: {sorted(unknown)}")

    pattern = body.get("pattern")
    if pattern is not None:
        try:
            re.compile(str(pattern))
        except re.error as exc:
            raise GithubEnvSetupError(f"Invalid pattern for {name}: {exc}") from exc

    description = body.get("description")
    return ValueDef(
        description=str(description) if description is not None else None,
        optional=bool(body.get("optional", False)),
        generate=bool(body.get("generate", False)),
        pattern=str(pattern) if pattern is not None else None,
    )


# ─── Env files ───────────────────────────────────────────────────────────────


def env_file_path(config_dir: Path, stage: str) -> Path:
    return config_dir / f"{ENV_FILE_PREFIX}{stage}"


def generate_secret(num_bytes: int = 32) -> str:
    return base64.b64encode(secrets.token_bytes(num_bytes)).decode("ascii")


def render_env_file(config: GithubEnvConfig, stage: str) -> str:
    config.resolve_stages(stage)
    lines = [
        f"# GitHub Environment values for: {stage}",
        f"# Fill in empty values, then run: make github-env-push STAGE={stage}",
        "# This file holds credentials. It is gitignored — never commit it.",
    ]
    lines += _render_section("Secrets", config.secrets, config.secrets)
    lines += _render_section("Variables", config.variables, {})
    lines.append("")
    return "\n".join(lines)


def render_missing_keys(config: GithubEnvConfig, existing_keys: set[str]) -> str:
    """Render only keys that are in the config but absent from an existing env file."""
    missing_secrets = {k: d for k, d in config.secrets.items() if k not in existing_keys}
    missing_variables = {k: d for k, d in config.variables.items() if k not in existing_keys}
    if not missing_secrets and not missing_variables:
        return ""

    lines = ["", "# ─── Added by setup-github-env (new keys) ───"]
    if missing_secrets:
        lines += _render_section("New Secrets", missing_secrets, missing_secrets)
    if missing_variables:
        lines += _render_section("New Variables", missing_variables, {})
    lines.append("")
    return "\n".join(lines)


def find_missing_keys(config: GithubEnvConfig, existing_keys: set[str]) -> list[str]:
    return [key for key in config.all_keys() if key not in existing_keys]


def _render_section(
    title: str,
    definitions: Mapping[str, ValueDef],
    secret_definitions: Mapping[str, ValueDef],
) -> list[str]:
    lines = ["", f"# ─── {title} ───"]
    for name, definition in definitions.items():
        description = f" — {definition.description}" if definition.description else ""
        is_generated = name in secret_definitions and definition.generate
        if is_generated:
            lines.append(f"# [auto-generated]{description}")
            lines.append(f"{name}={generate_secret()}")
            continue
        tag = "[optional]" if definition.optional else "[required]"
        lines.append(f"# {tag}{description}")
        lines.append(f"{name}=")
    return lines


def parse_env_file(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines; comments and blank lines are skipped, quotes are stripped."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env_file(config_dir: Path, stage: str) -> dict[str, str] | None:
    path = env_file_path(config_dir, stage)
    if not path.exists():
        return None
    return parse_env_file(path.read_text(encoding="utf-8"))


# ─── Validation ──────────────────────────────────────────────────────────────


def validate_value(name: str, definition: ValueDef, value: str) -> str | None:
    """Return an error message when the value violates the key's pattern, else None.

    The value itself is never included in the message so secrets cannot leak to logs.
    """
    if definition.pattern is None or re.fullmatch(definition.pattern, value):
        return None
    expected = definition.description or definition.pattern
    return f"{name} does not match the expected format ({expected})"


def validate_values(config: GithubEnvConfig, values: Mapping[str, str]) -> list[str]:
    errors: list[str] = []
    definitions = {**config.secrets, **config.variables}
    for name, definition in definitions.items():
        value = values.get(name)
        if value:
            error = validate_value(name, definition, value)
            if error is not None:
                errors.append(error)
    return errors


# ─── Core setup ──────────────────────────────────────────────────────────────


def setup_environment(
    gh: GhClient,
    repo: str,
    config: GithubEnvConfig,
    stage: str,
    ui: SetupUI,
    values: Mapping[str, str] | None = None,
    dry_run: bool = False,
) -> SetupResult:
    config.resolve_stages(stage)
    provided = dict(values or {})

    errors = validate_values(config, provided)
    if errors:
        raise GithubEnvSetupError("Invalid values:\n  - " + "\n  - ".join(errors))

    result = SetupResult()

    if dry_run:
        existing_secrets: set[str] = set()
        existing_variables: dict[str, str] = {}
    else:
        branch = config.environments[stage].branch
        ui.info(f'Ensuring GitHub environment "{stage}" exists...')
        gh.ensure_environment(repo, stage, branch)
        ui.success(f'Environment "{stage}" ready' + (f" (branch: {branch})" if branch else ""))
        existing_secrets = gh.list_secret_names(repo, stage)
        existing_variables = gh.list_variables(repo, stage)

    _sync_secrets(gh, repo, config, stage, ui, provided, existing_secrets, dry_run, result)
    _sync_variables(gh, repo, config, stage, ui, provided, existing_variables, dry_run, result)
    return result


def _sync_secrets(
    gh: GhClient,
    repo: str,
    config: GithubEnvConfig,
    stage: str,
    ui: SetupUI,
    provided: Mapping[str, str],
    existing_secrets: set[str],
    dry_run: bool,
    result: SetupResult,
) -> None:
    # Secret values cannot be read back from GitHub, so overwriting an existing one
    # is always an explicit choice; new secrets are pushed without asking.
    existing = [name for name in config.secrets if name in existing_secrets]
    overwrite = set(ui.confirm_overwrite(existing)) if existing else set()

    for name, definition in config.secrets.items():
        if name in existing_secrets and name not in overwrite:
            result.secrets_skipped.append(name)
            continue

        value = provided.get(name) or None
        if value is None and definition.generate:
            value = generate_secret()
            ui.info(f"Auto-generated {name}")
        if value is None and definition.optional:
            ui.info(f"Skipping optional secret {name}")
            result.secrets_skipped.append(name)
            continue
        if value is None and dry_run:
            ui.info(f"[dry-run] Would prompt for secret {name}")
            result.secrets_set.append(name)
            continue
        if value is None:
            value = _prompt_validated(ui, name, definition, stage, secret=True)
            if not value:
                ui.warn(f"Skipping {name} (empty value)")
                result.secrets_skipped.append(name)
                continue

        if dry_run:
            ui.info(f"[dry-run] Would set secret {name} on {stage}")
        else:
            gh.set_secret(repo, stage, name, value)
            ui.success(f"Secret {name} → {stage}")
        result.secrets_set.append(name)


def _sync_variables(
    gh: GhClient,
    repo: str,
    config: GithubEnvConfig,
    stage: str,
    ui: SetupUI,
    provided: Mapping[str, str],
    existing_variables: Mapping[str, str],
    dry_run: bool,
    result: SetupResult,
) -> None:
    for name, definition in config.variables.items():
        value = provided.get(name) or None

        if value is None and definition.optional:
            ui.info(f"Skipping optional variable {name}")
            result.variables_skipped.append(name)
            continue
        if value is None and dry_run:
            ui.info(f"[dry-run] Would prompt for variable {name}")
            result.variables_set.append(name)
            continue
        if value is None:
            value = _prompt_validated(ui, name, definition, stage, secret=False)
            if not value:
                ui.warn(f"Skipping variable {name} (empty value)")
                result.variables_skipped.append(name)
                continue

        if existing_variables.get(name) == value:
            ui.info(f"Variable {name} unchanged, skipping")
            result.variables_skipped.append(name)
            continue

        if dry_run:
            ui.info(f"[dry-run] Would set variable {name}={value} on {stage}")
        else:
            gh.set_variable(repo, stage, name, value)
            ui.success(f"Variable {name}={value} → {stage}")
        result.variables_set.append(name)


def _prompt_validated(
    ui: SetupUI, name: str, definition: ValueDef, stage: str, secret: bool
) -> str:
    value = ui.prompt_value(name, definition, stage, secret).strip()
    if value:
        error = validate_value(name, definition, value)
        if error is not None:
            raise GithubEnvSetupError(error)
    return value


# ─── gh CLI client ───────────────────────────────────────────────────────────


def parse_repo_slug(remote_url: str) -> str | None:
    """Extract owner/name from an https or ssh remote URL, including ssh host aliases."""
    match = _REPO_SLUG_PATTERN.search(remote_url.strip())
    return match.group("slug") if match else None


class GhCliClient:
    def check_ready(self, repo: str) -> str:
        """Verify gh is installed/authenticated with admin on the repo; return the login."""
        try:
            login = self._run(["api", "user", "-q", ".login"])
        except FileNotFoundError as exc:
            raise GithubEnvSetupError(
                "gh CLI is not installed. Install it: https://cli.github.com/"
            ) from exc

        is_admin = self._run(["api", f"repos/{repo}", "-q", ".permissions.admin"])
        if is_admin != "true":
            raise GithubEnvSetupError(
                f'gh account "{login}" lacks admin access to {repo}, which is required to '
                "manage environments and secrets. Switch to an admin account with: "
                "gh auth switch --user <login>"
            )
        return login

    def ensure_environment(self, repo: str, env: str, branch: str | None) -> None:
        if branch is None:
            self._run(["api", "--method", "PUT", f"repos/{repo}/environments/{env}"])
            return

        body = json.dumps(
            {
                "deployment_branch_policy": {
                    "protected_branches": False,
                    "custom_branch_policies": True,
                }
            }
        )
        self._run(
            ["api", "--method", "PUT", f"repos/{repo}/environments/{env}", "--input", "-"],
            stdin=body,
        )

        policies_path = f"repos/{repo}/environments/{env}/deployment-branch-policies"
        existing = self._run(["api", policies_path, "-q", ".branch_policies[].name"]).splitlines()
        if branch not in existing:
            self._run(
                [
                    "api",
                    "--method",
                    "POST",
                    policies_path,
                    "-f",
                    f"name={branch}",
                    "-f",
                    "type=branch",
                ]
            )

    def list_secret_names(self, repo: str, env: str) -> set[str]:
        output = self._run(["secret", "list", "--env", env, "--repo", repo, "--json", "name"])
        return {item["name"] for item in json.loads(output or "[]")}

    def list_variables(self, repo: str, env: str) -> dict[str, str]:
        output = self._run(
            ["variable", "list", "--env", env, "--repo", repo, "--json", "name,value"]
        )
        return {item["name"]: item["value"] for item in json.loads(output or "[]")}

    def set_secret(self, repo: str, env: str, name: str, value: str) -> None:
        # Value goes through stdin so it never appears in the process list.
        self._run(["secret", "set", name, "--env", env, "--repo", repo], stdin=value)

    def set_variable(self, repo: str, env: str, name: str, value: str) -> None:
        self._run(["variable", "set", name, "--env", env, "--repo", repo, "--body", value])

    def _run(self, args: list[str], stdin: str | None = None) -> str:
        completed = subprocess.run(
            ["gh", *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            # Report the subcommand only: argv may contain variable values, never secrets.
            raise GithubEnvSetupError(
                f"gh {' '.join(args[:3])} failed ({completed.returncode}): "
                f"{completed.stderr.strip()}"
            )
        return completed.stdout.strip()
