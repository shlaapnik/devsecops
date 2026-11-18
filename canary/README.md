# Canary

[Русская версия](README.ru.md)

The scanners of the pipeline update automatically. A defective scanner update can stop the
detection without an error. Then the check passes, but the scanner does not find issues.

This project contains known issues. The self-test runs each scanner update on this project. Then
`scripts/check_canary.py` examines the reports. Each report must contain each finding of
[expected.yml](expected.yml). If a finding is missing, the self-test fails. Then Renovate does not
merge the update.

A check that a report contains only "some" issues is not sufficient. A scanner update can stop
the detection for one file format and keep it for another. Thus the canary has a known issue for
each file format and each scanner, and the self-test examines each one.

| File | Scanner | Known issue |
| --- | --- | --- |
| `config.env` | Betterleaks | A false age secret key. |
| `allow-comment.env` | Betterleaks | The same key with a `gitleaks:allow` comment. The pipeline turns off these comments. |
| `app.py` | Semgrep | Command injection and eval injection from a request. The eval line has a `nosemgrep` comment. |
| `requirements.txt` | Grype | PyYAML 5.3 with critical vulnerabilities. |
| `pyproject.toml`, `uv.lock` | Grype | urllib3 1.23, a transitive dependency that is only in `uv.lock`. |
| `Dockerfile` | Grype on the built image | Alpine 3.10.0 with fixed vulnerabilities. |
| `bad.Dockerfile` | hadolint | `sudo` in `RUN`, and `ADD` under a `hadolint ignore` comment. |
| `.github/workflows/bad.yml` | zizmor, actionlint | `pull_request_target` and injection into `run`. |
| `.gitlab-ci.yml` | poutine | `curl \| sh` and `CI_DEBUG_TRACE`. |

To add a check or a file format:

1. Add a file with a known issue to this directory.
2. Run the canary and find the ID of the finding in the report.
3. Add the ID to `expected.yml`.

All secrets in this directory are false. GitHub and GitLab do not run the CI files in this
directory.
