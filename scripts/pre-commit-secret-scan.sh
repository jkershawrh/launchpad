#!/bin/bash
# Pre-commit hook: blocks commits containing secrets, API keys, or tokens.
# Install: cp scripts/pre-commit-secret-scan.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

RED='\033[0;31m'
NC='\033[0m'

# Patterns that should NEVER appear in committed code
PATTERNS=(
    'sk-[A-Za-z0-9]{16,}'           # LiteLLM/OpenAI API keys
    'sha256~[A-Za-z0-9]{20,}'       # OpenShift tokens
    'eyJ[A-Za-z0-9_-]{50,}'         # JWT tokens (base64-encoded)
    'password[[:space:]]*[:=][[:space:]]*"[^${\"]+' # Hardcoded passwords
    'PRIVATE KEY'                    # Private keys
    'BEGIN RSA'                      # RSA keys
    'BEGIN EC'                       # EC keys
)

FOUND=0
for pattern in "${PATTERNS[@]}"; do
    matches=$(git diff --cached --diff-filter=ACMR -U0 -- . ':!scripts/pre-commit-secret-scan.sh' ':!.github/workflows/ci.yml' | grep -E "^\+" | grep -v "^+++" | grep -cE "$pattern" 2>/dev/null)
    if [ "$matches" -gt 0 ]; then
        echo -e "${RED}BLOCKED: Found potential secret matching pattern: $pattern${NC}"
        git diff --cached --diff-filter=ACMR -U0 -- . ':!scripts/pre-commit-secret-scan.sh' ':!.github/workflows/ci.yml' | grep -E "^\+" | grep -v "^+++" | grep -E "$pattern" | head -3
        echo ""
        FOUND=1
    fi
done

# Check for known leaked key values via SHA-256 hash comparison.
# To add a new key: echo -n "the-secret-value" | shasum -a 256 | cut -d' ' -f1
KNOWN_HASHES=(
    '1663e133c58e4325d75d9f70840cb1f57245900c53fc598062c5560dd8ab28cd'
    'e47d44e22ece2564e9765b5e236ba1e664912ff5a2b505a714009479195dbcab'
    '1cf03a61fdb175275b59f8164761dff1bc88a2d605728dbc8ed686933684f709'
    '77000f84d3cc7e52204c7d26b849196e117b3bd6a29828338539cfbb516f5b8f'
    '59760228a77e677589b69c999f69dea65af808d2bae4a5a4a70caa266bfb3a8e'
)

DIFF_CONTENT=$(git diff --cached --diff-filter=ACMR -- . ':!scripts/pre-commit-secret-scan.sh' ':!.github/workflows/ci.yml' 2>/dev/null)
# Hash every token in one Python process. The previous shell loop spawned one
# `shasum` process per token and made a moderately sized commit take minutes.
KNOWN_MATCH=$(printf '%s' "$DIFF_CONTENT" | python3 -c '
import hashlib
import re
import sys

known = set(sys.argv[1:])
text = sys.stdin.read()
for word in re.findall(r"[A-Za-z0-9_-]+", text):
    if hashlib.sha256(word.encode()).hexdigest() in known:
        print("match")
        break
' "${KNOWN_HASHES[@]}")
if [ -n "$KNOWN_MATCH" ]; then
    echo -e "${RED}BLOCKED: Found known leaked secret value (hash match)${NC}"
    FOUND=1
fi

if [ "$FOUND" -eq 1 ]; then
    echo -e "${RED}Commit rejected. Remove secrets and use environment variables or K8s Secrets instead.${NC}"
    exit 1
fi

exit 0
