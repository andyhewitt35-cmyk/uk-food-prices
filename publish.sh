#!/usr/bin/env bash
# One-time publish of the grocery price comparison to GitHub Pages (free, HTTPS, refreshes twice a day via GitHub Actions).
# Needs:  gh auth login --hostname github.com --git-protocol https --web --scopes workflow
set -euo pipefail
cd "$(dirname "$0")"
REPO="${1:-uk-food-prices}"

gh auth status >/dev/null 2>&1 || { echo "Not logged in. Run: gh auth login --hostname github.com --git-protocol https --web --scopes workflow"; exit 1; }
gh auth status 2>&1 | grep -q "workflow" || { echo "Token lacks 'workflow' scope. Run: gh auth refresh -h github.com -s workflow"; exit 1; }
gh auth setup-git

OWNER="$(gh api user -q .login)"
UID_="$(gh api user -q .id)"
URL="https://${OWNER}.github.io/${REPO}/"

[ -d .git ] || git init -q -b main
git config user.name "$OWNER"
git config user.email "${UID_}+${OWNER}@users.noreply.github.com"
git add -A
git commit -qm "UK grocery price comparison" || true

if ! gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  gh repo create "$OWNER/$REPO" --public --description "UK supermarket price comparison (personal tool; data: Apify public dataset + Morrisons product pages)" \
    --homepage "$URL" --disable-wiki --disable-issues
fi
git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$OWNER/$REPO.git"

# Pages served from the Actions workflow (not from a branch)
gh api -X POST "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 \
  || gh api -X PUT "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null

git push -u origin main   # triggers the first build + deploy
sleep 8
RUN_ID="$(gh run list -R "$OWNER/$REPO" -L 1 --json databaseId -q '.[0].databaseId')"
gh run watch "$RUN_ID" -R "$OWNER/$REPO" --exit-status
echo "Published: $URL"
