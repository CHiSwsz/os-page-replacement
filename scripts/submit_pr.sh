#!/usr/bin/env bash
# Run after authenticating GitHub CLI with an account allowed to fork/create PRs.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
command -v gh >/dev/null 2>&1 || { echo 'Install GitHub CLI (gh), then run: gh auth login' >&2; exit 2; }
gh auth status >/dev/null 2>&1 || { echo 'Authenticate first: gh auth login' >&2; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo 'Commit or stash local edits before publishing this prepared branch.' >&2; exit 2; }
branch='codex/online-context-adaptive-v4'
[ "$(git branch --show-current)" = "$branch" ] || { echo "Switch to $branch first." >&2; exit 2; }
upstream='CHiSwsz/os-page-replacement'
login="$(gh api user --jq .login)"
fork="$login/os-page-replacement"
if [ "$login" = 'CHiSwsz' ]; then
    fork="$upstream"
elif ! gh repo view "$fork" >/dev/null 2>&1; then
    gh repo fork "$upstream" --clone=false
fi
if [ "$fork" != "$upstream" ]; then
    parent=''
    for attempt in {1..20}; do
        if parent="$(gh api "repos/$fork" --jq .parent.full_name 2>/dev/null)"; then break; fi
        sleep 1
    done
    [ "$parent" = "$upstream" ] || { echo "$fork is not a fork of $upstream; no push performed." >&2; exit 2; }
fi
git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push "https://github.com/$fork.git" "HEAD:refs/heads/$branch"
existing="$(gh api --method GET "repos/$upstream/pulls" -f state=open -f "head=$login:$branch" --jq '.[0].html_url // empty')"
if [ -n "$existing" ]; then printf '%s\n' "$existing"; exit 0; fi
gh pr create --repo "$upstream" --base main --head "$login:$branch" \
    --title 'Improve online adaptive paging and add classroom streaming runner' \
    --body-file PR_BODY.md
