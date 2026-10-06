from pathlib import Path

import pytest

from travel_data_platform.deployment.github_env import (
    GithubEnvSetupError,
    ValueDef,
    find_missing_keys,
    load_config,
    parse_config,
    parse_env_file,
    parse_repo_slug,
    render_env_file,
    render_missing_keys,
    setup_environment,
)

REPO = "owner/travel-data-platform"

CONFIG_TOML = """
[environments.prod]
branch = "main"

[secrets.DATABASE_URL]
description = "Neon direct URL"
pattern = 'postgresql\\+psycopg://\\S+'

[secrets.SIGNING_KEY]
generate = true

[secrets.OPTIONAL_TOKEN]
optional = true

[variables.LOG_LEVEL]
optional = true
pattern = "DEBUG|INFO|WARNING|ERROR"

[variables.REGION]
"""

VALID_URL = "postgresql+psycopg://u:p@ep-x.aws.neon.tech/neondb?sslmode=require"


class FakeGh:
    def __init__(
        self,
        secret_names: set[str] | None = None,
        variables: dict[str, str] | None = None,
    ) -> None:
        self.secret_names = secret_names or set()
        self.variables = variables or {}
        self.environments: list[tuple[str, str | None]] = []
        self.secrets_written: dict[str, str] = {}
        self.variables_written: dict[str, str] = {}

    def ensure_environment(self, repo: str, env: str, branch: str | None) -> None:
        self.environments.append((env, branch))

    def list_secret_names(self, repo: str, env: str) -> set[str]:
        return self.secret_names

    def list_variables(self, repo: str, env: str) -> dict[str, str]:
        return self.variables

    def set_secret(self, repo: str, env: str, name: str, value: str) -> None:
        self.secrets_written[name] = value

    def set_variable(self, repo: str, env: str, name: str, value: str) -> None:
        self.variables_written[name] = value


class FakeUI:
    def __init__(self, prompts: dict[str, str] | None = None, overwrite: list[str] | None = None):
        self.prompts = prompts or {}
        self.overwrite = overwrite or []
        self.prompted: list[tuple[str, bool]] = []
        self.overwrite_asked: list[str] = []

    def info(self, message: str) -> None:
        pass

    def success(self, message: str) -> None:
        pass

    def warn(self, message: str) -> None:
        pass

    def prompt_value(self, name: str, definition: ValueDef, stage: str, secret: bool) -> str:
        self.prompted.append((name, secret))
        return self.prompts.get(name, "")

    def confirm_overwrite(self, existing_names: list[str]) -> list[str]:
        self.overwrite_asked = existing_names
        return self.overwrite


@pytest.fixture
def config():
    return parse_config(CONFIG_TOML)


def test_repo_config_file_is_valid():
    repo_root = Path(__file__).resolve().parents[2]
    config = load_config(repo_root / "docs/deployment/github-envs.toml")

    assert config.environments["prod"].branch == "main"
    assert "DATABASE_URL" in config.secrets


def test_parse_config_rejects_generated_variables():
    with pytest.raises(GithubEnvSetupError, match="only supported for secrets"):
        parse_config("[environments.prod]\n[variables.X]\ngenerate = true\n")


def test_parse_config_rejects_unknown_options():
    with pytest.raises(GithubEnvSetupError, match="Unknown option"):
        parse_config("[environments.prod]\n[secrets.X]\nrequired = true\n")


def test_resolve_stages_rejects_unknown_stage(config):
    assert config.resolve_stages("all") == ["prod"]
    with pytest.raises(GithubEnvSetupError, match='Unknown stage "dev"'):
        config.resolve_stages("dev")


def test_render_env_file_prefills_generated_secrets_only(config):
    values = parse_env_file(render_env_file(config, "prod"))

    assert values["DATABASE_URL"] == ""
    assert values["OPTIONAL_TOKEN"] == ""
    assert values["LOG_LEVEL"] == ""
    assert len(values["SIGNING_KEY"]) == 44  # base64 of 32 bytes


def test_render_missing_keys_only_appends_new_keys(config):
    existing = {"DATABASE_URL", "SIGNING_KEY", "OPTIONAL_TOKEN", "LOG_LEVEL"}

    appended = parse_env_file(render_missing_keys(config, existing))

    assert set(appended) == {"REGION"}
    assert find_missing_keys(config, existing) == ["REGION"]
    assert render_missing_keys(config, existing | {"REGION"}) == ""


def test_parse_env_file_handles_comments_quotes_and_equals_in_values():
    values = parse_env_file(
        "# comment\n\nDATABASE_URL='postgresql+psycopg://u:p@h/db?sslmode=require'\nX=a=b\n"
    )

    assert values == {
        "DATABASE_URL": "postgresql+psycopg://u:p@h/db?sslmode=require",
        "X": "a=b",
    }


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("git@github.com:Apollosuny/travel-data-platform.git", "Apollosuny/travel-data-platform"),
        (
            "git@trung.github.com:Apollosuny/travel-data-platform.git",
            "Apollosuny/travel-data-platform",
        ),
        ("https://github.com/Apollosuny/travel-data-platform", "Apollosuny/travel-data-platform"),
        ("not-a-remote", None),
    ],
)
def test_parse_repo_slug(remote: str, expected: str | None):
    assert parse_repo_slug(remote) == expected


def test_setup_pushes_new_values_and_creates_environment(config):
    gh = FakeGh()
    ui = FakeUI()
    values = {"DATABASE_URL": VALID_URL, "LOG_LEVEL": "INFO", "REGION": "ap-southeast-1"}

    result = setup_environment(gh, REPO, config, "prod", ui, values=values)

    assert gh.environments == [("prod", "main")]
    assert gh.secrets_written["DATABASE_URL"] == VALID_URL
    assert len(gh.secrets_written["SIGNING_KEY"]) == 44
    assert "OPTIONAL_TOKEN" not in gh.secrets_written
    assert gh.variables_written == {"LOG_LEVEL": "INFO", "REGION": "ap-southeast-1"}
    assert result.secrets_skipped == ["OPTIONAL_TOKEN"]
    assert ui.prompted == []


def test_setup_rejects_invalid_values_before_touching_github(config):
    gh = FakeGh()
    values = {"DATABASE_URL": "postgresql://u:p@ep-x.aws.neon.tech/neondb"}

    with pytest.raises(GithubEnvSetupError, match="DATABASE_URL does not match") as exc_info:
        setup_environment(gh, REPO, config, "prod", FakeUI(), values=values)

    assert "u:p@" not in str(exc_info.value)
    assert gh.environments == []
    assert gh.secrets_written == {}


def test_setup_only_overwrites_confirmed_existing_secrets(config):
    gh = FakeGh(secret_names={"DATABASE_URL", "SIGNING_KEY"})
    ui = FakeUI(overwrite=["SIGNING_KEY"])
    values = {"DATABASE_URL": VALID_URL, "SIGNING_KEY": "rotated", "REGION": "x"}

    result = setup_environment(gh, REPO, config, "prod", ui, values=values)

    assert ui.overwrite_asked == ["DATABASE_URL", "SIGNING_KEY"]
    assert gh.secrets_written == {"SIGNING_KEY": "rotated"}
    assert "DATABASE_URL" in result.secrets_skipped


def test_setup_skips_unchanged_variables(config):
    gh = FakeGh(variables={"REGION": "x"})

    result = setup_environment(
        gh, REPO, config, "prod", FakeUI(), values={"DATABASE_URL": VALID_URL, "REGION": "x"}
    )

    assert "REGION" not in gh.variables_written
    assert "REGION" in result.variables_skipped


def test_setup_prompts_for_missing_required_values_and_validates_them(config):
    gh = FakeGh()
    ui = FakeUI(prompts={"DATABASE_URL": VALID_URL, "REGION": "y"})

    setup_environment(gh, REPO, config, "prod", ui, values=None)

    assert ("DATABASE_URL", True) in ui.prompted
    assert ("REGION", False) in ui.prompted
    assert gh.secrets_written["DATABASE_URL"] == VALID_URL

    bad_ui = FakeUI(prompts={"DATABASE_URL": "mysql://nope"})
    with pytest.raises(GithubEnvSetupError, match="DATABASE_URL does not match"):
        setup_environment(FakeGh(), REPO, config, "prod", bad_ui, values=None)


def test_dry_run_never_calls_github_or_prompts(config):
    gh = FakeGh()
    ui = FakeUI()

    result = setup_environment(gh, REPO, config, "prod", ui, values={}, dry_run=True)

    assert gh.environments == []
    assert gh.secrets_written == {}
    assert gh.variables_written == {}
    assert ui.prompted == []
    assert "DATABASE_URL" in result.secrets_set
