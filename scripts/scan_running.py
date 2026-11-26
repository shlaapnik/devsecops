"""Scan the images of running containers with Grype and send what has a fix to Telegram.

CI scans a fresh build. A server runs images built days or weeks ago, and a CVE published since
then hits them with no pipeline running. Run this nightly on the server, by cron:

    DEVSECOPS_TELEGRAM_TOKEN=... DEVSECOPS_TELEGRAM_CHAT_ID=... \\
        python3 scan_running.py --project myapp --config /srv/myapp/.grype.yaml

`--project` takes the images of one Compose project, `--image` names images one by one, and
nothing else on the host is scanned. Grype gets each image from `docker save` on its stdin, so the
scanner container has no Docker socket. Only the standard library: the server's python3 runs it.
With `--state` a message goes out only when a package and CVE appear that the last message did
not have: a third-party image waiting for its fix does not repeat every night.

Exit codes: 0 nothing at the threshold, 1 fixable vulnerabilities at the threshold or above,
3 the scan, the message or the script failed.
"""

import argparse
import html
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# The -debug variant has a shell, which writes stdin to a file for Grype.
GRYPE_IMAGE = (
    "anchore/grype:v0.122.1-debug@sha256:123579d16feeadc9f1a6b28d8bc27edeead34a1ff37d6784070f61af669391ef"
)
RANK = {"negligible": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SHOWN = 5  # packages per image in the message; Telegram cuts a message at 4096 characters


class ScanFailed(Exception):
    pass


@dataclass
class Package:
    name: str
    version: str
    severity: str = "Unknown"
    ids: set[str] = field(default_factory=set)
    fixes: set[str] = field(default_factory=set)

    def line(self) -> str:
        ids = sorted(self.ids)
        more = f" +{len(ids) - 1}" if len(ids) > 1 else ""
        return f"{self.name} {self.version} → {', '.join(sorted(self.fixes))}: {ids[0]} {self.severity}{more}"


def rank(severity: str) -> int:
    return RANK.get(severity.lower(), 0)


def vulnerable(report: dict, threshold: str) -> list[Package]:
    """The packages of a Grype JSON report with a vulnerability at the threshold or above, worst first."""
    packages: dict[tuple[str, str], Package] = {}
    for match in report.get("matches") or []:
        vulnerability, artifact = match["vulnerability"], match["artifact"]
        severity = vulnerability.get("severity", "Unknown")
        if rank(severity) < RANK[threshold]:
            continue
        key = (artifact["name"], artifact["version"])
        package = packages.setdefault(key, Package(*key))
        package.ids.add(vulnerability["id"])
        package.fixes.update(vulnerability.get("fix", {}).get("versions", []))
        if rank(severity) > rank(package.severity):
            package.severity = severity
    return sorted(packages.values(), key=lambda p: (-rank(p.severity), p.name))


def message(title: str, found: Mapping[str, Sequence[Package]], total: int | None = None) -> str:
    """Telegram HTML: the title, then each vulnerable image with its worst packages. With `total`
    the packages are the new ones, and the last line counts all of them."""
    what = "new fixable vulnerabilities" if total is not None else "fixable vulnerabilities"
    lines = [f"🔴 <b>{html.escape(title)}</b>: {what} in running images"]
    for image, packages in found.items():
        lines.append(f"<b>{html.escape(image)}</b>")
        lines += [f"• {html.escape(package.line())}" for package in packages[:SHOWN]]
        if len(packages) > SHOWN:
            lines.append(f"… {len(packages) - SHOWN} more packages")
    if total is not None:
        lines.append(f"Vulnerable packages in all running images: {total}")
    return "\n".join(lines)


def repository(image: str) -> str:
    """The image without its tag or digest: a rebuild of the same image is not a new finding."""
    name = image.split("@", 1)[0]
    head, _, tail = name.rpartition(":")
    return head if head and "/" not in tail else name


def keys(image: str, package: Package) -> set[str]:
    return {f"{repository(image)} {package.name} {vulnerability}" for vulnerability in package.ids}


def only_new(found: Mapping[str, Sequence[Package]], seen: set[str]) -> dict[str, list[Package]]:
    """The packages with a vulnerability the last message did not have."""
    new = {image: [p for p in packages if keys(image, p) - seen] for image, packages in found.items()}
    return {image: packages for image, packages in new.items() if packages}


def images_by_name(inspect_output: str) -> dict[str, str]:
    """`docker inspect` lines of `{{.Config.Image}} {{.Image}}`: each image name without its digest,
    and the image ID. An image pulled by digest (`name:tag@sha256:…`, as Renovate pins them) has no
    local tag, so `docker save name:tag` does not find it and the ID does."""
    pairs = (line.split() for line in inspect_output.splitlines() if line.strip())
    return {reference.split("@", 1)[0]: image_id for reference, image_id in pairs}


def running_images(project: str) -> dict[str, str]:
    """The images of the running containers of one Compose project: name and image ID."""
    command = ["docker", "ps", "--quiet", "--filter", f"label=com.docker.compose.project={project}"]
    containers = subprocess.run(command, check=True, capture_output=True, text=True).stdout.split()
    if not containers:
        return {}
    command = ["docker", "inspect", "--format", "{{.Config.Image}} {{.Image}}", *containers]
    return images_by_name(subprocess.run(command, check=True, capture_output=True, text=True).stdout)


def scan(image: str, config: Path | None, cache: str) -> dict:
    """Grype's JSON report of one image. One CPU and 2 GB at most: the host may run other services."""
    command = ["docker", "run", "--rm", "--interactive", "--cpus", "1", "--memory", "2g"]
    # Grype runs as nonroot: a new volume on its home takes the owner of that folder, a new
    # volume elsewhere is root's and the database download fails.
    command += ["--volume", f"{cache}:/home/nonroot", "--env", "GRYPE_DB_CACHE_DIR=/home/nonroot/grype-db"]
    grype = ["/grype", "docker-archive:/tmp/image.tar", "--only-fixed", "--output", "json"]
    if config:
        command += ["--volume", f"{config.resolve()}:/grype.yaml:ro"]
        grype += ["--config", "/grype.yaml"]
    command += ["--entrypoint", "/busybox/sh", GRYPE_IMAGE, "-c", 'cat > /tmp/image.tar && exec "$@"', "sh"]
    with subprocess.Popen(["docker", "save", image], stdout=subprocess.PIPE) as save:
        result = subprocess.run(command + grype, stdin=save.stdout, capture_output=True, text=True)
        if save.stdout:
            save.stdout.close()
    if save.returncode or result.returncode:
        codes = f"docker save {save.returncode}, grype {result.returncode}"
        raise ScanFailed(f"{codes}\n{result.stderr[-500:]}")
    return json.loads(result.stdout)


def send(token: str, chat: str, text: str) -> None:
    body = urllib.parse.urlencode(
        {"chat_id": chat, "text": text, "parse_mode": "HTML", "link_preview_options": '{"is_disabled":true}'}
    ).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ScanFailed(f"Telegram answered {response.status}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    raw = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=raw)
    parser.add_argument("--project", help="scan the images of this running Compose project")
    parser.add_argument("--image", action="append", default=[], help="an image to scan; repeat for more")
    parser.add_argument("--config", type=Path, help="Grype config with reviewed ignores, usually .grype.yaml")
    parser.add_argument("--fail-on", choices=list(RANK), default="high", help="lowest severity that counts")
    parser.add_argument("--cache", default="devsecops-grype-db", help="Docker volume of the Grype database")
    parser.add_argument("--title", help="name in the message; the project by default")
    parser.add_argument(
        "--state", type=Path, help="file of the findings already sent: a message only for new ones"
    )
    parser.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    return parser.parse_args(argv)


def main(argv: Iterable[str]) -> int:
    args = parse_args(list(argv))
    images = {image: image for image in args.image}
    if args.project:
        images |= running_images(args.project)
    if not images:
        print("No images to scan", file=sys.stderr)
        return 3
    found: dict[str, list[Package]] = {}
    for name, image in sorted(images.items()):
        try:
            packages = vulnerable(scan(image, args.config, args.cache), args.fail_on)
        except (ScanFailed, json.JSONDecodeError) as error:
            print(f"Scan failed: {name}: {error}", file=sys.stderr)
            return 3
        print(f"{name}: {len(packages)} vulnerable package(s)")
        if packages:
            found[name] = packages
    current = {
        key for image, packages in found.items() for package in packages for key in keys(image, package)
    }
    report: Mapping[str, Sequence[Package]] = found
    total = None
    if args.state:
        seen = set(json.loads(args.state.read_text())) if args.state.exists() else set()
        report, total = only_new(found, seen), sum(len(packages) for packages in found.values())
    if report:
        text = message(args.title or args.project or "server", report, total)
        token = os.environ.get("DEVSECOPS_TELEGRAM_TOKEN")
        chat = os.environ.get("DEVSECOPS_TELEGRAM_CHAT_ID")
        if args.dry_run or not token or not chat:
            print(text)  # not delivered: the state stays, the next run sends it
            return 1
        try:
            send(token, chat, text)
        # The token is in the URL, and some errors quote it (http.client.InvalidURL on a stray
        # character from the env file): only the type of the error is printed.
        except Exception as error:
            print(f"Telegram message failed: {type(error).__name__}", file=sys.stderr)
            return 3
    if args.state and not args.dry_run:
        args.state.write_text(json.dumps(sorted(current), indent=0))
    return 1 if found else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as error:  # Python exits with 1 on a crash, and 1 means findings
        print(f"Failed: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(3)
