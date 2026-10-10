#!/bin/sh
# Pre-commit guard: refuse to commit anything that looks like an API key.
# Installed by `make hooks`. Checks only lines being added in this commit.
set -eu

PATTERNS='tabpfn_sk_[A-Za-z0-9_-]{10,}|rnd_[A-Za-z0-9]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|sk-[A-Za-z0-9]{32,}'

if git diff --cached -U0 --no-color | grep -E '^\+[^+]' | grep -Eq "$PATTERNS"; then
    echo "check-secrets: a staged change looks like an API key. Move it to .env (gitignored)." >&2
    git diff --cached --name-only -G "$PATTERNS" | sed 's/^/  /' >&2
    exit 1
fi

for f in $(git diff --cached --name-only); do
    case "$f" in
        .env|.env.*) [ "$f" = ".env.example" ] || { echo "check-secrets: refusing to commit $f" >&2; exit 1; } ;;
    esac
done
