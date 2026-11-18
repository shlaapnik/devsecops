"""Check that the reports of a canary run contain every finding of canary/expected.yml.

uv run scripts/check_canary.py github <reports-dir>
"""

import argparse
import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict, cast

import yaml

logger = logging.getLogger(__name__)

EXPECTED = Path(__file__).resolve().parent.parent / "canary" / "expected.yml"


class SarifRun(TypedDict, total=False):
    """The part of a SARIF run that holds the findings."""

    results: list[dict[str, object]]


class Sarif(TypedDict, total=False):
    """A SARIF report."""

    runs: list[SarifRun]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("platform", choices=["github", "gitlab"])
    parser.add_argument("reports", type=Path, help="directory with the report files of the run")
    return parser.parse_args(argv)


def expected_findings(expected: Path, platform: str) -> dict[str, list[str]]:
    """Return the required findings of each report file on the platform."""
    sections = yaml.safe_load(expected.read_text(encoding="utf-8"))
    return {**sections["common"], **sections[platform]}


def findings_text(report: Path) -> str:
    """Return the findings of a report as text.

    A SARIF report also lists every rule that ran, so only its results count. Suppressed results
    count too, like in the gate: Semgrep marks a finding under nosemgrep as suppressed even with
    --disable-nosem. An actionlint JSON report is a list of findings.

    Raises:
        ValueError: The report is not valid JSON.
    """
    data = json.loads(report.read_text(encoding="utf-8"))
    if report.suffix == ".sarif":
        return json.dumps([run.get("results", []) for run in cast(Sarif, data).get("runs", [])])
    return json.dumps(data)


def missing_findings(reports: Path, expected: Mapping[str, list[str]]) -> list[str]:
    """Return a message for each absent report and for each finding that a report does not contain."""
    missing = []
    for report, findings in expected.items():
        path = reports / report
        if not path.is_file():
            missing.append(f"{report}: the report is absent")
            continue
        try:
            text = findings_text(path)
        except ValueError:
            missing.append(f"{report}: the report is not valid JSON")
            continue
        missing += [f"{report}: {finding} is not found" for finding in findings if finding not in text]
    return missing


def main(argv: list[str]) -> int:
    """Log the missing findings and return 1 if there are any."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    expected = expected_findings(EXPECTED, args.platform)
    missing = missing_findings(args.reports, expected)
    for message in missing:
        logger.error(message)
    if missing:
        return 1
    logger.info("All %d canary findings are found.", sum(len(findings) for findings in expected.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
