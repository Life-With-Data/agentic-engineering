#!/usr/bin/env bash
#
# record_gh_fixtures.sh — record real gh JSON fixtures for the lifecycle tests.
#
# WHY THIS EXISTS
#   The plan prohibits hand-written mock JSON: tier-1 unit tests in
#   lifecycle_board_test.py replay RECORDED gh output so a future gh JSON-shape
#   change surfaces as a fixture diff, not a silent test lie. This script is the
#   single sanctioned way to (re)generate those fixtures. Re-run it whenever the
#   pinned gh version changes or the recorded issues/PRs drift.
#
# WHAT IT RECORDS  (into tests/fixtures/gh/)
#   issue_view_closed.json    a closed issue: state, stateReason,
#                             closedByPullRequestsReferences
#   pr_view_merged.json       a merged PR: number, state, mergedAt,
#                             baseRefName, headRefName
#   issue_list_deps.json      gh issue list --json number,title,assignees,
#                             blockedBy,parent --limit 5
#   project_field_list.json   gh project field-list (SKIPPED with a note if the
#   project_item_list.json    gh project item-list  owner has no project yet —
#                             board bootstrap lands in Phase 4)
#
#   Each fixture gets a sibling <name>.meta line recording the gh version, the
#   UTC date, and the exact command used — provenance for the recorded shape.
#
# REQUIREMENTS
#   gh >= 2.94.0, authenticated to github.com (`gh auth status`).
#   All gh calls carry an explicit --repo/--owner (fork-trap discipline).
#
# USAGE
#   bash plugins/agentic-engineering/tests/record_gh_fixtures.sh
#
set -euo pipefail

REPO="aagnone3/agentic-engineering"
OWNER="aagnone3"

# Resolve the fixtures dir relative to this script (not the caller's cwd).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="${SCRIPT_DIR}/fixtures/gh"
mkdir -p "${FIXTURES_DIR}"

# Preflight: gh present + authenticated.
if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI not found on PATH. Install gh >= 2.94.0." >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh is not authenticated (\`gh auth status\` failed)." >&2
  exit 1
fi

GH_VERSION="$(gh --version | head -n1)"
NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# write_meta <fixture_path> <command string>
write_meta() {
  local fixture="$1"
  local cmd="$2"
  printf 'recorded_at=%s | %s | cmd: %s\n' \
    "${NOW_UTC}" "${GH_VERSION}" "${cmd}" >"${fixture}.meta"
}

echo "Recording gh fixtures into ${FIXTURES_DIR}"
echo "  gh: ${GH_VERSION}"
echo

# ---------------------------------------------------------------------------
# 1. A closed issue: pick the most recent closed issue, then view its full
#    lifecycle-relevant shape. Reconciler repairs key on stateReason +
#    closedByPullRequestsReferences.
# ---------------------------------------------------------------------------
CLOSED_ISSUE="$(gh issue list --repo "${REPO}" --state closed --limit 1 \
  --json number --jq '.[0].number')"
if [[ -z "${CLOSED_ISSUE}" || "${CLOSED_ISSUE}" == "null" ]]; then
  echo "SKIP issue_view_closed.json: no closed issues in ${REPO}." >&2
else
  CMD="gh issue view ${CLOSED_ISSUE} --repo ${REPO} --json state,stateReason,closedByPullRequestsReferences,number,title"
  eval "${CMD}" >"${FIXTURES_DIR}/issue_view_closed.json"
  write_meta "${FIXTURES_DIR}/issue_view_closed.json" "${CMD}"
  echo "  wrote issue_view_closed.json   (issue #${CLOSED_ISSUE})"
fi

# ---------------------------------------------------------------------------
# 2. A merged PR: mergedAt distinguishes merged from closed-unmerged;
#    baseRefName drives the merged_to_non_default_branch report-only flag.
# ---------------------------------------------------------------------------
MERGED_PR="$(gh pr list --repo "${REPO}" --state merged --limit 1 \
  --json number --jq '.[0].number')"
if [[ -z "${MERGED_PR}" || "${MERGED_PR}" == "null" ]]; then
  echo "SKIP pr_view_merged.json: no merged PRs in ${REPO}." >&2
else
  CMD="gh pr view ${MERGED_PR} --repo ${REPO} --json number,state,mergedAt,baseRefName,headRefName"
  eval "${CMD}" >"${FIXTURES_DIR}/pr_view_merged.json"
  write_meta "${FIXTURES_DIR}/pr_view_merged.json" "${CMD}"
  echo "  wrote pr_view_merged.json      (PR #${MERGED_PR})"
fi

# ---------------------------------------------------------------------------
# 3. issue list with dependency fields: the ready-work / reconciler read shape.
# ---------------------------------------------------------------------------
CMD="gh issue list --repo ${REPO} --json number,title,assignees,blockedBy,parent --limit 5"
eval "${CMD}" >"${FIXTURES_DIR}/issue_list_deps.json"
write_meta "${FIXTURES_DIR}/issue_list_deps.json" "${CMD}"
echo "  wrote issue_list_deps.json"

# ---------------------------------------------------------------------------
# 4 & 5. Project fixtures: require a board under ${OWNER}. Board bootstrap
#        lands in Phase 4, so gracefully SKIP (leaving a .skip note) when the
#        owner has no project yet.
# ---------------------------------------------------------------------------
FIRST_PROJECT="$(gh project list --owner "${OWNER}" --format json \
  --jq '.projects[0].number' 2>/dev/null || true)"
if [[ -z "${FIRST_PROJECT}" || "${FIRST_PROJECT}" == "null" ]]; then
  NOTE="no GitHub Project exists for owner ${OWNER} yet (board bootstrap lands in Phase 4); re-run after bootstrap to record."
  printf 'SKIPPED %s | %s | %s\n' "${NOW_UTC}" "${GH_VERSION}" "${NOTE}" \
    >"${FIXTURES_DIR}/project_field_list.json.skip"
  printf 'SKIPPED %s | %s | %s\n' "${NOW_UTC}" "${GH_VERSION}" "${NOTE}" \
    >"${FIXTURES_DIR}/project_item_list.json.skip"
  echo "  SKIP project_field_list.json / project_item_list.json: ${NOTE}"
else
  CMD="gh project field-list ${FIRST_PROJECT} --owner ${OWNER} --format json"
  eval "${CMD}" >"${FIXTURES_DIR}/project_field_list.json"
  write_meta "${FIXTURES_DIR}/project_field_list.json" "${CMD}"
  echo "  wrote project_field_list.json  (project #${FIRST_PROJECT})"

  CMD="gh project item-list ${FIRST_PROJECT} --owner ${OWNER} --format json --limit 20"
  eval "${CMD}" >"${FIXTURES_DIR}/project_item_list.json"
  write_meta "${FIXTURES_DIR}/project_item_list.json" "${CMD}"
  echo "  wrote project_item_list.json   (project #${FIRST_PROJECT})"
fi

echo
echo "Done. Fixtures in ${FIXTURES_DIR}:"
ls -1 "${FIXTURES_DIR}"
