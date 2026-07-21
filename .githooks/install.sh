#!/bin/sh
# Opt-in installer for the versioned git hooks in .githooks/.
#
# Installs a small shim into the clone's shared hooks directory
# (`$(git rev-parse --git-common-dir)/hooks`) rather than setting
# core.hooksPath: hooksPath REPLACES the hook search path and silently
# disables hooks other tools have installed into .git/hooks (see
# docs/solutions/integration-issues/skills-mutating-user-repos-git-gotchas.md,
# lesson 6). The shim re-resolves .githooks/pre-commit in whichever worktree
# the commit runs from, so one install covers every worktree of the clone and
# branches without .githooks/ are a clean no-op.
set -eu

marker="agentic-engineering .githooks shim"

hookspath="$(git config --get core.hooksPath || true)"
if [ -n "$hookspath" ]; then
    echo "hooks:install: core.hooksPath is set to '$hookspath'." >&2
    echo "hooks:install: git consults ONLY that directory (it replaces .git/hooks)," >&2
    echo "hooks:install: so a shim installed here would never fire. Instead, add" >&2
    echo "hooks:install: this line to the pre-commit hook in that directory:" >&2
    echo '  "$(git rev-parse --show-toplevel)/.githooks/pre-commit"' >&2
    exit 1
fi

hooks_dir="$(git rev-parse --git-common-dir)/hooks"
target="$hooks_dir/pre-commit"
mkdir -p "$hooks_dir"

if [ -e "$target" ] && ! grep -q "$marker" "$target" 2>/dev/null; then
    echo "hooks:install: $target exists and was not installed by this script." >&2
    echo "hooks:install: refusing to overwrite it. To chain, append this line to it:" >&2
    echo '  "$(git rev-parse --show-toplevel)/.githooks/pre-commit"' >&2
    exit 1
fi

cat > "$target" <<'EOF'
#!/bin/sh
# agentic-engineering .githooks shim -- installed by `bun run hooks:install`.
# Delegates to the versioned hook in the current worktree; a checkout
# without .githooks/ is a clean no-op.
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
hook="$root/.githooks/pre-commit"
[ -x "$hook" ] && exec "$hook"
exit 0
EOF
chmod +x "$target"

echo "hooks:install: pre-commit shim installed at $target"
echo "hooks:install: it runs .githooks/pre-commit in every worktree of this clone."
