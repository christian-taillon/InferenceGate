#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
hook_path="$repo_root/.git/hooks/pre-commit"

cat > "$hook_path" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
python_bin="$repo_root/.venv/bin/python"

if [ ! -x "$python_bin" ]; then
    printf 'pre-commit: FAIL - missing %s\n' "$python_bin" >&2
    exit 1
fi

printf 'pre-commit: running ruff check...\n'
if ! (cd "$repo_root" && "$python_bin" -m ruff check . --quiet); then
    printf 'pre-commit: FAIL - ruff check failed\n' >&2
    exit 1
fi

printf 'pre-commit: running firewall tests...\n'
if ! (cd "$repo_root" && "$python_bin" -m pytest tests/test_firewall.py -q --tb=short); then
    printf 'pre-commit: FAIL - firewall tests failed\n' >&2
    exit 1
fi

printf 'pre-commit: PASS\n'
EOF

chmod +x "$hook_path"
printf 'Installed pre-commit hook at %s\n' "$hook_path"
