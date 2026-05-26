#!/usr/bin/env bash
# Set up branch protection on all three platform repos.
# Requires: gh CLI authenticated with admin access to rhpds org.
#
# Usage: bash scripts/setup-branch-protection.sh

set -euo pipefail

REPOS=("rhpds/launchpad" "rhpds/stargate")
# Add "rhpds/deepfield" once the repo is created

for REPO in "${REPOS[@]}"; do
  echo "Setting branch protection on $REPO..."

  gh api \
    --method PUT \
    "repos/$REPO/branches/main/protection" \
    --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Tests + Lint"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF

  echo "Done: $REPO"
done

echo ""
echo "Branch protection configured on: ${REPOS[*]}"
echo ""
echo "To add DeepField later:"
echo '  gh api --method PUT repos/rhpds/deepfield/branches/main/protection --input <same JSON>'
