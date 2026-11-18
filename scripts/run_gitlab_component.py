"""Run the jobs of the GitLab component in their own images, the way a Docker-executor runner does.

The project is copied into a temporary git repository with world-writable files, because runners
use umask 0000. Inputs are interpolated, `extends` and `!reference` are resolved, and every job runs
with `docker run`. With --expect the run fails unless every scan job exits with that code.

    uv run scripts/run_gitlab_component.py canary --input enforce=false --expect 2
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict, cast

import yaml

logger = logging.getLogger(__name__)

COMPONENT = Path(__file__).resolve().parent.parent / "templates" / "devsecops.yml"
WORKDIR = "/builds/project"
BUILD_JOBS = frozenset({"devsecops-image-build"})
INPUT = re.compile(r"\$\[\[ inputs\.([\w-]+) \]\]")
CONDITION = re.compile(r'\$(\w+)(?: (==|=~) (?:"([^"]*)"|/(.+)/))?')
VARIABLE = re.compile(r"\$(\w+)")


class Reference(list[str]):
    """Job name and key of a `!reference` tag."""


type ScriptItem = str | Reference | list[ScriptItem]

Rule = TypedDict("Rule", {"if": str, "when": str}, total=False)


class Image(TypedDict):
    """Image of a job."""

    name: str


class Job(TypedDict, total=False):
    """The job keys this runner understands."""

    extends: str
    image: Image
    variables: dict[str, str]
    rules: list[Rule | Reference]
    script: list[ScriptItem]


type Config = dict[str, Job]


class ComponentLoader(yaml.SafeLoader):
    """Safe YAML loader that understands the GitLab `!reference` tag."""


def construct_reference(loader: ComponentLoader, node: yaml.SequenceNode) -> Reference:
    """Build a reference from a `!reference [job, key]` node."""
    return Reference(loader.construct_sequence(node))


ComponentLoader.add_constructor("!reference", construct_reference)


def parse_input(value: str) -> tuple[str, str]:
    """Split a `key=value` input override."""
    key, separator, input_value = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError(f"expected KEY=VALUE, got {value!r}")
    return key, input_value


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("--input", type=parse_input, action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--expect", type=int, help="exit code every scan job must return")
    parser.add_argument("--docker-arg", action="append", default=[], help="extra `docker run` argument")
    parser.add_argument(
        "--keep-reports", type=Path, metavar="DIR", help="copy the job reports to this directory"
    )
    return parser.parse_args(argv)


def load_config(component: Path, overrides: Mapping[str, str]) -> Config:
    """Return the component jobs with the inputs interpolated.

    Raises:
        ValueError: An override names an input the component does not declare.
    """
    spec_text, body = component.read_text(encoding="utf-8").split("\n---\n", 1)
    inputs = yaml.safe_load(spec_text)["spec"]["inputs"]
    unknown = set(overrides) - set(inputs)
    if unknown:
        raise ValueError(f"Unknown inputs: {', '.join(sorted(unknown))}")
    values = {}
    for name, spec in inputs.items():
        default = spec.get("default", "")
        values[name] = str(default).lower() if isinstance(default, bool) else str(default)
    values.update(overrides)
    loader = ComponentLoader(INPUT.sub(lambda match: values[match.group(1)], body))
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def merge(base: Mapping[str, object], extra: Mapping[str, object]) -> dict[str, object]:
    """Merge two mappings like GitLab `extends`: nested mappings merge, everything else is replaced."""
    merged = dict(base)
    for key, value in extra.items():
        current = merged.get(key)
        if isinstance(value, Mapping) and isinstance(current, Mapping):
            merged[key] = merge(current, value)
        else:
            merged[key] = value
    return merged


def resolve(config: Config, name: str) -> Job:
    """Return a job with its `extends` chain applied."""
    job = config[name]
    parent = job.get("extends")
    if parent is None:
        return job
    own = {key: value for key, value in job.items() if key != "extends"}
    return cast(Job, merge(resolve(config, parent), own))


def flatten(config: Config, script: list[ScriptItem]) -> list[str]:
    """Return script lines with `!reference` tags and nested lists expanded.

    Raises:
        ValueError: A reference points to a key other than `script`.
    """
    lines: list[str] = []
    for item in script:
        if isinstance(item, Reference):
            job_name, key = item
            if key != "script":
                raise ValueError(f"Only !reference [job, script] is supported, got {item}")
            lines.extend(flatten(config, config[job_name]["script"]))
        elif isinstance(item, list):
            lines.extend(flatten(config, item))
        else:
            lines.append(item)
    return lines


def flatten_rules(config: Config, rules: list[Rule | Reference]) -> list[Rule]:
    """Return rules with `!reference [job, rules]` tags expanded."""
    flat: list[Rule] = []
    for rule in rules:
        if isinstance(rule, Reference):
            flat.extend(flatten_rules(config, config[rule[0]].get("rules", [])))
        else:
            flat.append(rule)
    return flat


def matches(condition: str, env: Mapping[str, str]) -> bool:
    """Evaluate an `if` of `&&`-joined `$VAR`, `$VAR == "text"` and `$VAR =~ /regex/` terms.

    Raises:
        ValueError: A term has another form.
    """
    for term in condition.split(" && "):
        match = CONDITION.fullmatch(term.strip())
        if match is None:
            raise ValueError(f"Unsupported rules:if term: {term}")
        name, operator, text, pattern = match.groups()
        value = env.get(name, "")
        if operator == "==" and value != text:
            return False
        if operator == "=~" and not re.search(pattern, value):
            return False
        if operator is None and not value:
            return False
    return True


def is_added(config: Config, job: Job, env: Mapping[str, str]) -> bool:
    """Apply the first matching rule, like GitLab: no match or `when: never` leaves the job out."""
    if "rules" not in job:
        return True
    for rule in flatten_rules(config, job["rules"]):
        if "if" not in rule or matches(rule["if"], env):
            return rule.get("when", "on_success") != "never"
    return False


def job_env(job: Job, branch: str) -> dict[str, str]:
    """Return the predefined CI variables and the job variables, expanded in order."""
    env = {
        "CI_PROJECT_DIR": WORKDIR,
        "CI_CONFIG_PATH": ".gitlab-ci.yml",
        "CI_DEFAULT_BRANCH": branch,
        "CI_COMMIT_BRANCH": branch,
        "CI_PIPELINE_SOURCE": "push",
        "CI_SERVER_URL": "https://gitlab.com",
    }
    for key, value in job.get("variables", {}).items():
        env[key] = VARIABLE.sub(lambda match: env.get(match.group(1), ""), str(value))
    return env


def prepare_workspace(project: Path, parent: Path) -> Path:
    """Copy the project into a world-writable git repository under `parent`."""
    workspace = parent / "project"
    shutil.copytree(project, workspace, ignore=shutil.ignore_patterns("devsecops-reports", "devsecops-image"))
    if not (workspace / ".git").exists():
        git = ["git", "-C", str(workspace), "-c", "user.name=test", "-c", "user.email=test@example.com"]
        subprocess.run([*git, "init", "--quiet", "--initial-branch", "main"], check=True)
        subprocess.run(
            [*git, "remote", "add", "origin", "https://gitlab.com/example/project.git"], check=True
        )
        subprocess.run([*git, "add", "--all"], check=True)
        subprocess.run([*git, "commit", "--quiet", "--message", "test"], check=True)
    for root, dirs, files in os.walk(workspace):
        for entry in [*dirs, *files]:
            os.chmod(os.path.join(root, entry), 0o777)
    os.chmod(workspace, 0o777)
    return workspace


def current_branch(workspace: Path) -> str:
    """Return the checked-out branch, `main` for a detached HEAD."""
    command = ["git", "-C", str(workspace), "branch", "--show-current"]
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip() or "main"


def run_job(config: Config, name: str, workspace: Path, docker_args: list[str]) -> int | None:
    """Run one job in its image and return its exit code, or None when its rules skip it."""
    job = resolve(config, name)
    env = job_env(job, current_branch(workspace))
    if not is_added(config, job, env):
        logger.info("--- %s: skipped by rules", name)
        return None
    # A runner cleans untracked files before each job and runs the job script with umask 0000.
    shutil.rmtree(workspace / "devsecops-reports", ignore_errors=True)
    command = ["docker", "run", "--rm", "--entrypoint", "", "--volume", f"{workspace}:{WORKDIR}"]
    command += ["--workdir", WORKDIR, *docker_args]
    for key, value in env.items():
        command += ["--env", f"{key}={value}"]
    script = "\n".join(["set -e", "umask 0000", *flatten(config, job["script"])])
    command += [job["image"]["name"], "sh", "-c", script]
    logger.info("--- %s: %s", name, job["image"]["name"].split("@")[0])
    return subprocess.run(command, check=False).returncode


def unexpected(results: Mapping[str, int | None], expect: int | None) -> list[str]:
    """Log the results table and return the jobs whose exit code differs from the expected one."""
    logger.info("\n%-24s%s", "job", "exit")
    failed = []
    for name, code in results.items():
        expected = 0 if name in BUILD_JOBS else expect
        mismatch = code is not None and expected is not None and code != expected
        verdict = f"expected {expected}" if mismatch else ""
        logger.info("%-24s%-8s%s", name, "skipped" if code is None else code, verdict)
        if mismatch:
            failed.append(name)
    return failed


def keep_reports(workspace: Path, destination: Path) -> None:
    """Copy the reports of the last job to `destination`."""
    reports = workspace / "devsecops-reports"
    if reports.is_dir():
        shutil.copytree(reports, destination, dirs_exist_ok=True)


def main(argv: list[str]) -> int:
    """Run every job of the component on a project and compare the exit codes."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    try:
        config = load_config(COMPONENT, dict(args.input))
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    with tempfile.TemporaryDirectory(prefix="devsecops-gitlab-", ignore_cleanup_errors=True) as temp:
        workspace = prepare_workspace(args.project, Path(temp))
        results: dict[str, int | None] = {}
        for name in [name for name in config if not name.startswith(".")]:
            results[name] = run_job(config, name, workspace, args.docker_arg)
            if args.keep_reports:
                keep_reports(workspace, args.keep_reports)
    return 1 if unexpected(results, args.expect) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
