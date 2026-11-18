# devsecops

[Русская версия](README.ru.md)

This repository contains a DevSecOps pipeline for GitHub Actions and GitLab CI. The pipeline
examines secrets, code, dependencies, Dockerfiles, container images and CI configuration. The
pipeline updates its scanners automatically. A canary test examines each scanner update before
the update goes into the pipeline.

## Quick start

Your project does not contain a copy of the pipeline. Your project contains a short file with a
reference to a release of this repository. When a new release is available, Renovate updates the
reference.

1. Clone this repository:

   ```bash
   git clone --depth 1 https://github.com/shlaapnik/devsecops
   ```

2. Run the script for your project:

   ```bash
   devsecops/scripts/bootstrap.sh path/to/your-project
   ```

   The script finds the platform from the `origin` remote of the project. The script adds the
   pipeline file, the Renovate configuration and the exception files. The script does not change
   the files that exist.

3. Do the steps in the `todo` and `next` lines of the script output.

Example of the output for a new GitHub project:

```text
platform github, pipeline version v0.1.0
add   .github/workflows/devsecops.yml
add   .betterleaksignore
...
add   renovate.json

next  commit the changes:
        cd path/to/your-project
        git add .github/workflows/devsecops.yml .betterleaksignore ... renovate.json
        git commit -m "Add the DevSecOps pipeline"
next  install the Renovate app in the repository: https://github.com/apps/renovate
next  in the branch ruleset, make "Scan / Gate" a required check
```

NOTE: The script needs bash and git. On Windows, use Git Bash.

To install the pipeline without the script, do the steps in [Install on GitHub](#install-on-github)
or [Install on GitLab](#install-on-gitlab).

## Checks

| Check | GitHub Actions | GitLab CI | The check fails when |
| --- | --- | --- | --- |
| Secrets in the git history | Betterleaks | Betterleaks | Betterleaks finds a secret with medium or high confidence |
| CI configuration | zizmor, actionlint | poutine | zizmor finds a medium or high issue, or actionlint or poutine finds an issue |
| Code | Semgrep CE, `p/default` | Semgrep CE, `p/default` | a rule with the ERROR level finds an issue |
| Dependencies | Grype | Grype | a vulnerability is high or critical and a fixed version exists |
| Dockerfiles | hadolint | hadolint | hadolint finds an error |
| Container image | Docker, Grype | kaniko, Grype | a vulnerability is high or critical and a fixed version exists |

A vulnerability without a fixed version does not stop the pipeline. An update cannot remove this
type of vulnerability.

Grype shows the EPSS value for each vulnerability. EPSS is the probability that attackers use
the vulnerability in the next 30 days.

Each job keeps its reports as run artifacts. The reports are SARIF files and CycloneDX SBOM files.
In public GitHub repositories, the pipeline also sends the SARIF files to code scanning. On GitLab,
the jobs publish SAST, CycloneDX and code quality reports.

## Install on GitHub

1. Add the file `.github/workflows/devsecops.yml` to your project:

   ```yaml
   name: DevSecOps
   on:
     push:
       branches: [main]
     pull_request:
     schedule:
       - cron: "23 3 * * *"
   permissions: {}
   jobs:
     scan:
       name: Scan
       uses: shlaapnik/devsecops/.github/workflows/scan.yml@<commit-sha> # vX.Y.Z
       permissions:
         actions: read
         contents: read
         security-events: write
   ```

2. Replace `<commit-sha>` and `vX.Y.Z` with the values of the latest release. Keep the comment.
   Renovate uses it to find the release.
3. Add the file `renovate.json` with the content `{"extends": ["github>shlaapnik/devsecops"]}`.
4. Install the [Renovate app](https://github.com/apps/renovate) in your repository.
5. In the branch ruleset of your repository, make `Scan / Gate` a required check.

NOTE: The nightly run finds new vulnerabilities in code that did not change.

NOTE: Renovate merges a pull request only when all required checks pass.

The script in [Quick start](#quick-start) does steps 1 to 3. The script also adds the exception
files.

## Install on GitLab

1. Add this `include` to `.gitlab-ci.yml`:

   ```yaml
   include:
     - remote: https://raw.githubusercontent.com/shlaapnik/devsecops/<commit-sha>/templates/devsecops.yml # vX.Y.Z
       inputs:
         enforce: true
   ```

2. Replace `<commit-sha>` and `vX.Y.Z` with the values of the latest release. Keep the comment.
   Renovate uses it to find the release.
3. Make sure that the project has the `test` stage. If it does not, set the `stage` input.
4. Make sure that your runners use the Docker executor or the Kubernetes executor.
5. Make sure that your runners use the default `umask 0000`.
6. Configure Renovate in a separate project. Do this one time for all projects of a group. Use the
   file [onboarding/gitlab-renovate-bot/.gitlab-ci.yml](onboarding/gitlab-renovate-bot/.gitlab-ci.yml).
7. Add a nightly pipeline schedule to your project.

The script in [Quick start](#quick-start) does step 1. The script also adds the exception files.

NOTE: The jobs do not use privileged mode. kaniko builds the image without a Docker daemon.

NOTE: By default, the jobs run in branch pipelines only. Thus the include does not add a merge
request pipeline to your project. If your project already runs merge request pipelines, set
`merge-request-pipelines: true`. Then the jobs run in the merge request pipeline, and not again in
the branch pipeline.

The jobs use these exit codes:

| Code | Meaning | Job status |
| --- | --- | --- |
| 0 | The scanner found no issues. | passed |
| 1 | The scanner found issues and `enforce` is `true`. | failed |
| 2 | The scanner found issues and `enforce` is `false`, or an exception file changed. | passed with a warning |
| 3 | The scanner did not work. | failed |

You can also mirror this repository to your GitLab instance. Then use the file as a CI/CD
component: `component: $CI_SERVER_FQDN/<group>/devsecops/devsecops@<version>`.

## Updates

### Scanner updates

1. Renovate finds a new scanner version.
2. Renovate waits 7 days after the release date.
3. Renovate opens a pull request in this repository.
4. The self-test runs the GitHub and GitLab pipelines on [canary/](canary/).
5. If a scanner does not find each finding of [canary/expected.yml](canary/expected.yml), the self-test fails.
6. If the self-test passes, Renovate merges the minor or patch update.

NOTE: A person must examine each major update.

NOTE: Only Docker Hub gives the release date of an image. For images from other registries, for
example ghcr.io, Renovate cannot wait 7 days. Renovate opens the pull request immediately, and a
person merges it 7 days after the release.

NOTE: In March 2026, attackers published a malicious Trivy release. The Trivy team removed it in
less than one day. The 7-day delay prevents this type of attack.

### Dependency updates in your project

The shared Renovate preset [default.json](default.json) does these steps:

- It pins actions, images and dependencies to a digest.
- It waits 7 days before it proposes a usual update.
- It proposes a vulnerability fix immediately.
- It merges patch, digest, pin and lock file updates when all checks pass.
- It merges minor updates of packages with version 1.0 or higher when all checks pass.
- It updates the lock files each week. This adds fixes for transitive dependencies.
- It does not merge updates of images from registries other than Docker Hub. These registries do
  not give the release date, so Renovate cannot wait 7 days. A person merges these updates.

Renovate cannot delay transitive updates and the weekly lock file update. Set the same delay in
your package manager:

- uv: add `exclude-newer = "7 days"` to the `[tool.uv]` table in `pyproject.toml`.
- pnpm: add `minimumReleaseAge: 10080` to `pnpm-workspace.yaml`.
- npm 11.10 or later: add `min-release-age=7` to `.npmrc`.
- Yarn 4.10 or later: add `npmMinimalAgeGate: 10080` to `.yarnrc.yml`.

The script `bootstrap.sh` shows the missing setting as a `todo` line.

### Pipeline updates in your project

Your project uses the commit SHA of a release. A tag can move to a different commit, but a SHA
cannot. The comment after the SHA shows the release. Renovate updates the SHA and the comment in
a separate pull request:

- On GitHub, in the `uses` line of the workflow.
- On GitLab, in the `include: remote` URL. The shared preset contains the rule for this URL.

You can also use `main` in place of the SHA. Then your project gets each change without a pull
request. Renovate does not change `main`. On GitHub, zizmor accepts `main` because of the line
`"shlaapnik/devsecops/*": ref-pin` in `.github/zizmor.yml`.

## Incompatible updates

Renovate does not know if a new version is compatible. Renovate uses the version number and your
CI checks.

- Renovate does not merge a major update. A person or an AI agent must do the migration.
- Renovate does not merge minor updates of `0.x` packages. These updates can change the API.
- Renovate merges patch updates only when all required checks pass.

CAUTION: Automatic merge is only as safe as your tests. If your project has no tests, a defective
patch update can pass the checks. Add tests, or remove automatic merge from that project.

A new scanner version can find more issues. This is not a compatibility error, but your checks
can fail.

- If your project pins a release, the new issues show in the Renovate pull request. You see them
  before the merge.
- If your project uses `@main`, the new issues show in the next run.

## Inputs

| Input | Default | Function |
| --- | --- | --- |
| `enforce` | `true` | Set `false` to show issues without a failure. GitLab shows a warning. |
| `skip` | empty | Checks to skip, with commas: `secrets`, `ci`, `sast`, `deps`, `dockerfiles`, `image`. |
| `fail-on-severity` | `high` | The lowest severity of a fixable vulnerability that stops the pipeline. |
| `secrets-confidence` | `medium` | The lowest Betterleaks confidence that the report shows. |
| `semgrep-config` | `p/default` | Semgrep rulesets, with spaces. The pipeline adds the `.semgrep/` directory automatically. |
| `semgrep-args` | empty | More Semgrep arguments. |
| `dockerfile` | `Dockerfile` | The Dockerfile for the image check. |
| `docker-context` | `.` | The build context for the image check. |
| `path` | `.` | The directory to scan in a monorepo. |
| `upload-sarif` | `true` | GitHub only. Sends SARIF to code scanning. The pipeline skips private repositories. |
| `report-name` | `devsecops` | GitHub only. The artifact prefix, if one run calls the workflow two times. |
| `stage` | `test` | GitLab only. The stage of the jobs. |
| `merge-request-pipelines` | `false` | GitLab only. Set `true` if the project runs merge request pipelines. |

## Add the pipeline to an existing project

1. Set `enforce: false` for the first runs.
2. Read the summary of the run.
3. Fix the issues that you can fix.
4. Record the other issues as exceptions. Use the table below.
5. Set `enforce: true`.

`scripts/bootstrap.sh` adds the exception files. Each file contains an example. If you do not use
the script, copy the files from [onboarding/](onboarding/).

The script does not change or replace a file that exists:

- A tool can read its configuration under more than one name. If a file exists under one of these
  names, the script does not add a file. A new file can hide the existing file.
- If an existing file must contain a setting of the pipeline, the script shows a `todo` line. The
  line tells which setting to add and where. Add the setting manually.
- The script shows a `keep` line for each existing file.

| File that the script adds | Other names that the script examines |
| --- | --- |
| `.github/workflows/devsecops.yml` | Each workflow that calls `scan.yml`. |
| `renovate.json` | `renovate.json5`, `.github/renovate.json`, `.github/renovate.json5`, `.gitlab/renovate.json`, `.gitlab/renovate.json5`, `.renovaterc`, `.renovaterc.json`, `.renovaterc.json5`, the `renovate` section of `package.json`. |
| `.betterleaksignore` | `.gitleaksignore` |
| `.grype.yaml` | `.grype.yml`, `.grype/config.yaml`, `.grype/config.yml` |
| `.hadolint.yaml` | `.hadolint.yml` |
| `.github/zizmor.yml` | `zizmor.yml` |
| `.github/actionlint.yaml` | `.github/actionlint.yml` |
| `.poutine.yml` | `.github/poutine.yml` |

| Issue | Exception file |
| --- | --- |
| A false secret, or a secret that you replaced | Add the fingerprint to `.betterleaksignore`. |
| Many old secrets in the git history | Make a baseline. Use the command below. |
| A vulnerability that you cannot fix now | Add it to `.grype.yaml`. Write the reason and a review date. |
| Test data with vulnerable dependencies | Add the path to `exclude` in `.grype.yaml`, for example `./tests/data/**`. |
| A false SAST issue | Add the path to `.semgrepignore`, or set `semgrep-args: --exclude-rule <id>`. |
| A CI configuration rule | Use `.github/zizmor.yml`, `.github/actionlint.yaml` or `.poutine.yml`. |
| A hadolint rule | Add it to `.hadolint.yaml`, for example `ignored: [DL3008]`. |

To make a baseline of secrets, replace the secrets first. Then run this command:

```bash
docker run --rm -v "$PWD:/src" -w /src ghcr.io/betterleaks/betterleaks:v1.10.0 \
  git --redact --confidence medium --exit-code 0 \
  --report-format json --report-path .devsecops/betterleaks-baseline.json .
```

Example of `.grype.yaml`:

```yaml
ignore:
  - vulnerability: GHSA-xxxx-xxxx-xxxx
    reason: The project does not call the vulnerable code. Review before 2026-12-15.
```

## AI agents

The exceptions are only in files that show in a review. An AI agent can add an inline comment to
make a check pass. Thus the pipeline ignores these inline comments: `nosemgrep`, `gitleaks:allow`,
`betterleaks:allow` and `# hadolint ignore=`.

The pipeline shows a warning when a pull request does one of these changes:

- It changes an exception file.
- It changes a pipeline setting, for example `enforce` or `skip`. On GitHub, the pipeline examines
  the workflow that calls `scan.yml`. On GitLab, it examines `.gitlab-ci.yml`.
- It adds or removes a `# zizmor: ignore` comment in a GitHub workflow or action. zizmor obeys
  these comments.

Use an AI agent for these tasks:

- Migration. If a Renovate update breaks the build, tell the agent to do the migration in the same
  pull request.
- Fixes. The summary and the annotations show the file and the line of each issue. The agent can
  use this data to fix the issue.
- Dependabot alerts. If you have GitHub Code Security, you can assign the alerts to an agent.

## Limits

- Semgrep downloads `p/default` from its registry in each run. New rules can appear without a
  change in this repository.
- GitHub stops scheduled workflows after 60 days without activity in the repository.
- The image check builds the image without build arguments or secrets.
- kaniko must have registry credentials for a private base image.
- GitLab.com limits each artifact to 1 GB. A large image can be larger than this limit.
- If the image check cannot work in your project, set `skip: image`. Then scan the published image
  in your deployment pipeline.
- Dependabot can show alerts for the dependencies in `canary/` of this repository. This is correct:
  the canary contains these vulnerabilities on purpose.

## Not included

- DAST, for example ZAP or Nuclei. DAST must have a running environment. Add DAST to your
  deployment pipeline.
- Terraform and Kubernetes files. Use Checkov or `trivy config`.
- Image signatures and admission control. Use cosign and Kyverno in your deployment pipeline.
- ML models in the pickle format. Use ModelScan or ModelAudit. The safetensors format is safer.

## Repository files

```text
.github/workflows/scan.yml       The reusable GitHub workflow.
.github/workflows/self-test.yml  The scan and lint of this repository, and the canary runs.
templates/devsecops.yml          The GitLab CI/CD component.
default.json                     The shared Renovate preset for projects.
renovate.json                    The Renovate configuration of this repository.
canary/                          The project with known issues for the self-test.
onboarding/                      The files that bootstrap.sh copies into a project.
onboarding/gitlab-renovate-bot/  The separate Renovate project for GitLab. The script does not copy it.
scripts/                         The bootstrap script, the GitLab component runner and the canary check.
```

## License

[MIT](LICENSE)
