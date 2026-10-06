"""Generate and push GitHub Environment secrets/variables for the workflows.

Usage (from the repository root):
    uv run python -m travel_data_platform.deployment.setup_github_env --init prod
    uv run python -m travel_data_platform.deployment.setup_github_env --stage prod --dry-run
    uv run python -m travel_data_platform.deployment.setup_github_env --stage prod

Step 1 `--init` writes docs/deployment/.env.github.<stage> (gitignored) with every
key from github-envs.toml; re-running it only appends keys added to the config.
Step 2 fill in the empty values. Step 3 `--stage` creates the GitHub Environment
(with its branch policy) and pushes the values with the gh CLI.
"""

import argparse
import getpass
import subprocess
import sys
from pathlib import Path

from travel_data_platform.deployment.github_env import (
    GhCliClient,
    GithubEnvConfig,
    GithubEnvSetupError,
    ValueDef,
    env_file_path,
    find_missing_keys,
    load_config,
    load_env_file,
    parse_env_file,
    parse_repo_slug,
    render_env_file,
    render_missing_keys,
    setup_environment,
)

DEFAULT_CONFIG_PATH = Path("docs/deployment/github-envs.toml")

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_RED = "\x1b[31m"
_CYAN = "\x1b[36m"


class TerminalUI:
    def info(self, message: str) -> None:
        print(f"{_CYAN}ℹ{_RESET} {message}")

    def success(self, message: str) -> None:
        print(f"{_GREEN}✔{_RESET} {message}")

    def warn(self, message: str) -> None:
        print(f"{_YELLOW}⚠{_RESET} {message}")

    def prompt_value(self, name: str, definition: ValueDef, stage: str, secret: bool) -> str:
        description = f" {_DIM}({definition.description}){_RESET}" if definition.description else ""
        prompt = f"Enter {_BOLD}{name}{_RESET} for {stage}{description}: "
        # Secrets are read without echo so they do not end up in terminal scrollback.
        return getpass.getpass(prompt) if secret else input(prompt)

    def confirm_overwrite(self, existing_names: list[str]) -> list[str]:
        self.warn("These secrets already exist on GitHub (values cannot be read back):")
        selected: list[str] = []
        for name in existing_names:
            answer = input(f"  Overwrite {_BOLD}{name}{_RESET}? [y/N]: ").strip().lower()
            if answer in {"y", "yes"}:
                selected.append(name)
        return selected


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("-i", "--init", metavar="STAGE", help="Generate .env.github.<STAGE> (or all)")
    mode.add_argument("-s", "--stage", metavar="STAGE", help="Push values to GitHub (or all)")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--repo", help="owner/name; defaults to the origin remote")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    return parser.parse_args(argv)


def _run_init(config: GithubEnvConfig, config_dir: Path, stages: list[str], ui: TerminalUI) -> None:
    for stage in stages:
        path = env_file_path(config_dir, stage)

        if not path.exists():
            path.write_text(render_env_file(config, stage), encoding="utf-8")
            ui.success(f"Created {path}")
            ui.info(f"Fill in empty values, then run: make github-env-push STAGE={stage}")
            continue

        existing_keys = set(parse_env_file(path.read_text(encoding="utf-8")))
        appended = render_missing_keys(config, existing_keys)
        if not appended:
            ui.success(f"{path} is up to date — no new keys")
            continue

        with path.open("a", encoding="utf-8") as handle:
            handle.write(appended)
        ui.success(f"Appended new key(s) to {path}:")
        for name in find_missing_keys(config, existing_keys):
            print(f"  {_DIM}+{_RESET} {name}")


def _resolve_repo(explicit_repo: str | None) -> str:
    if explicit_repo:
        return explicit_repo

    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=False
    )
    slug = parse_repo_slug(remote.stdout) if remote.returncode == 0 else None
    if slug is None:
        raise GithubEnvSetupError("Could not detect owner/name from the origin remote; pass --repo")
    return slug


def _run_push(
    config: GithubEnvConfig,
    config_dir: Path,
    stages: list[str],
    repo: str,
    dry_run: bool,
    ui: TerminalUI,
) -> None:
    gh = GhCliClient()
    if dry_run:
        ui.warn("DRY RUN — no changes will be made")
    else:
        login = gh.check_ready(repo)
        ui.info(f"gh account: {_BOLD}{login}{_RESET}")
    ui.info(f"Repository: {_BOLD}{repo}{_RESET}")

    for stage in stages:
        print(f"\n{_BOLD}━━━ {stage} ━━━{_RESET}")
        values = load_env_file(config_dir, stage)
        if values is None:
            ui.warn(f"No {env_file_path(config_dir, stage)} found — will prompt for all values")
        else:
            ui.info(f"Loaded values from {env_file_path(config_dir, stage)}")
            missing = find_missing_keys(config, set(values))
            if missing:
                ui.warn(f"Env file is missing {len(missing)} key(s): {', '.join(missing)}")
                ui.info(f"Tip: run make github-env-init STAGE={stage} to add them")

        result = setup_environment(gh, repo, config, stage, ui, values=values, dry_run=dry_run)
        print(
            f"\n  Secrets: {len(result.secrets_set)} set, {len(result.secrets_skipped)} skipped"
            f"\n  Variables: {len(result.variables_set)} set, "
            f"{len(result.variables_skipped)} skipped"
        )

    ui.success("All done!")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ui = TerminalUI()

    try:
        config = load_config(args.config)
        config_dir = args.config.parent
        if args.init:
            _run_init(config, config_dir, config.resolve_stages(args.init), ui)
        else:
            stages = config.resolve_stages(args.stage)
            _run_push(config, config_dir, stages, _resolve_repo(args.repo), args.dry_run, ui)
    except (GithubEnvSetupError, FileNotFoundError) as exc:
        print(f"{_RED}✖{_RESET} {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n{_YELLOW}⚠{_RESET} Aborted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
