#!/usr/bin/env bash
# Add the DevSecOps pipeline to a project.
#
#   scripts/bootstrap.sh <project-dir> [--github | --gitlab] [--ref <tag> | --ref main]
#
# The platform is guessed from the origin remote. By default the project is pinned to the commit
# of the latest release, with the tag in a comment so Renovate can bump both; --ref main follows
# the main branch.
set -euo pipefail

repo="shlaapnik/devsecops"
root="$(cd "$(dirname "$0")/.." && pwd)"
# The repository is public: git must fail, not ask for a password.
export GIT_TERMINAL_PROMPT=0

target=""
platform=""
ref=""
while (( $# > 0 )); do
  case "$1" in
    --github) platform=github ;;
    --gitlab) platform=gitlab ;;
    --ref) ref="${2:?--ref needs a value}"; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) target="$1" ;;
  esac
  shift
done
if [[ -z "$target" || ! -d "$target" ]]; then
  echo "usage: scripts/bootstrap.sh <project-dir> [--github | --gitlab] [--ref <tag> | --ref main]" >&2
  exit 2
fi

if [[ -z "$platform" ]]; then
  # The host of the origin remote: https://host/..., ssh://user@host:port/... or user@host:path.
  host=$(git -C "$target" remote get-url origin 2>/dev/null \
    | sed -E 's#^[a-z+]+://##; s#^[^@/]*@##; s#[:/].*##' || true)
  case "$host" in
    *github*) platform=github ;;
    *gitlab*) platform=gitlab ;;
    *)
      platform=github
      echo "note  the origin remote does not show the platform: using github, give --gitlab for GitLab"
      ;;
  esac
fi

if [[ -z "$ref" ]]; then
  tags=$(git ls-remote --tags --refs "https://github.com/$repo.git" 'v*') \
    || { echo "error: cannot read the releases of $repo" >&2; exit 1; }
  ref=$(grep -oE 'refs/tags/v[0-9]+\.[0-9]+\.[0-9]+$' <<< "$tags" | cut -d / -f 3 | sort -V | tail -n 1 || true)
  if [[ -z "$ref" ]]; then
    echo "note  no release of $repo yet, following main"
    ref=main
  fi
fi

# A tag can move to another commit, a commit cannot change. So both platforms use the commit.
pin="$ref"
pin_note=""
if [[ "$ref" != "main" ]]; then
  tags=$(git ls-remote "https://github.com/$repo.git" "refs/tags/$ref" "refs/tags/$ref^{}") \
    || { echo "error: cannot read the tags of $repo" >&2; exit 1; }
  # An annotated tag points to a tag object. Its commit is on the "<tag>^{}" line.
  pin=$(awk -v tag="refs/tags/$ref" '$2 == tag "^{}" { peeled = $1 } $2 == tag { plain = $1 }
    END { print (peeled != "" ? peeled : plain) }' <<< "$tags")
  if [[ -z "$pin" ]]; then
    echo "error: tag $ref not found in $repo" >&2
    exit 1
  fi
  pin_note=" # $ref"
fi

# Print an onboarding file with the pipeline version in place of __REF__.
render() {
  sed "s|__REF__\(.*\)|$pin\1$pin_note|" "$1"
}

added=()
copy() {
  local src="$root/onboarding/$platform/$1" dst="$target/$1"
  if [[ ! -f "$src" ]]; then
    src="$root/onboarding/$1"
  fi
  mkdir -p "$(dirname "$dst")"
  render "$src" > "$dst"
  added+=("$1")
  echo "add   $1"
}

was_added() {
  [[ " ${added[*]-} " == *" $1 "* ]]
}

todos=0
todo() {
  echo "todo  $*"
  todos=$((todos + 1))
}

# Print the first of the paths that exists in the project.
existing() {
  local path
  for path in "$@"; do
    if [[ -e "$target/$path" ]]; then
      echo "$path"
      return 0
    fi
  done
  return 1
}

# True if one of the files in the project contains the text.
mentions() {
  local text="$1" path
  shift
  for path in "$@"; do
    if grep -qs -- "$text" "$target/$path"; then
      return 0
    fi
  done
  return 1
}

echo "platform $platform, pipeline version $ref"

if [[ "$platform" == github ]]; then
  caller=$(grep -rl "$repo/.github/workflows/scan.yml" "$target/.github/workflows" 2>/dev/null | head -n 1 || true)
  if [[ -n "$caller" ]]; then
    echo "keep  ${caller#"$target/"} (already calls the pipeline)"
  elif found=$(existing .github/workflows/devsecops.yml); then
    todo "$found exists: add the scan job from onboarding/github/$found to it"
  else
    copy .github/workflows/devsecops.yml
  fi
elif found=$(existing .gitlab-ci.yml); then
  if grep -q "$repo" "$target/$found"; then
    echo "keep  $found (already includes the pipeline)"
  else
    todo "add this include to $found:"
    render "$root/onboarding/gitlab/.gitlab-ci.yml" | sed 's/^/        /'
  fi
else
  copy .gitlab-ci.yml
fi

# The first name is the file to add. The tool also reads the other names, so an existing file
# under any of them stays, and the new file never hides it.
exceptions=(
  ".betterleaksignore .gitleaksignore"
  ".semgrepignore"
  ".grype.yaml .grype.yml .grype/config.yaml .grype/config.yml"
  ".hadolint.yaml .hadolint.yml"
)
if [[ "$platform" == github ]]; then
  exceptions+=(".github/zizmor.yml zizmor.yml" ".github/actionlint.yaml .github/actionlint.yml")
else
  exceptions+=(".poutine.yml .github/poutine.yml")
fi
for names in "${exceptions[@]}"; do
  read -r -a candidates <<< "$names"
  if found=$(existing "${candidates[@]}"); then
    echo "keep  $found (already exists)"
  else
    copy "${candidates[0]}"
  fi
done
if [[ "$platform" == github && "$ref" == main ]] && found=$(existing .github/zizmor.yml zizmor.yml) \
  && ! grep -q "$repo" "$target/$found"; then
  todo "allow the main branch: add \"$repo/*\": ref-pin to the unpinned-uses policies in $found"
fi

renovate_configs=(renovate.json renovate.json5 .github/renovate.json .github/renovate.json5
  .gitlab/renovate.json .gitlab/renovate.json5 .renovaterc .renovaterc.json .renovaterc.json5)
if found=$(existing "${renovate_configs[@]}"); then
  if grep -q "$repo" "$target/$found"; then
    echo "keep  $found (already extends the preset)"
  else
    todo "add \"github>$repo\" to \"extends\" in $found"
  fi
elif [[ -f "$target/package.json" ]] && grep -q '"renovate"' "$target/package.json"; then
  todo "add \"github>$repo\" to \"extends\" in the renovate section of package.json"
else
  copy renovate.json
fi

if ! found=$(existing .pre-commit-config.yaml); then
  copy .pre-commit-config.yaml
elif grep -q betterleaks "$target/$found"; then
  echo "keep  $found (already has the hooks)"
else
  todo "merge the hooks from onboarding/$platform/$found into $found"
fi

# Renovate cannot delay transitive dependencies and the weekly lock file update. The package
# manager can, so it gets the same 7 days.
if [[ -f "$target/uv.lock" ]] && ! mentions exclude-newer pyproject.toml uv.toml; then
  todo 'uv cooldown: add exclude-newer = "7 days" under [tool.uv] in pyproject.toml'
fi
if [[ -f "$target/pnpm-lock.yaml" ]] && ! mentions minimumReleaseAge pnpm-workspace.yaml; then
  todo "pnpm cooldown: add minimumReleaseAge: 10080 to pnpm-workspace.yaml"
fi
if [[ -f "$target/package-lock.json" ]] && ! mentions min-release-age .npmrc; then
  todo "npm 11.10+ cooldown: add min-release-age=7 to .npmrc"
fi
if [[ -f "$target/.yarnrc.yml" ]] && ! mentions npmMinimalAgeGate .yarnrc.yml; then
  todo "Yarn 4.10+ cooldown: add npmMinimalAgeGate: 10080 to .yarnrc.yml"
fi

# The steps that the script cannot do, in the order to do them.
echo
if (( todos > 0 )); then
  echo "next  do the todo steps above"
fi
if was_added .github/workflows/devsecops.yml || was_added .gitlab-ci.yml; then
  echo "next  an old project can have many findings: uncomment enforce: false for the first runs"
fi
if (( ${#added[@]} > 0 )); then
  echo "next  commit the changes:"
  printf '        cd %q\n' "$target"
  echo "        git add ${added[*]}"
  echo '        git commit -m "Add the DevSecOps pipeline"'
fi
if [[ "$platform" == github ]]; then
  echo "next  install the Renovate app in the repository: https://github.com/apps/renovate"
  echo 'next  in the branch ruleset, make "Scan / Gate" a required check'
else
  echo "next  one time for the group: make a renovate-bot project from onboarding/gitlab-renovate-bot/"
  echo 'next  in Settings > Merge requests, turn on "Pipelines must succeed"'
  echo "next  add a nightly schedule of the default branch in Build > Pipeline schedules: it finds new CVEs"
fi
if was_added .pre-commit-config.yaml; then
  echo "next  optional: run pre-commit install to find secrets before each commit"
fi
