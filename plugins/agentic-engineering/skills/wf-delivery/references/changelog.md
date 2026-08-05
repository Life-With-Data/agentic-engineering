# Changelog

Derive user-facing release notes from the changes merged since the last
release.

## Gather

1. Determine the window: since the last release tag, or the requested period.
2. List merged PRs in the window with `gh pr list --state merged` (add
   `--repo <origin>` explicitly). Pull each PR's title, number, labels, body,
   and linked issues.
3. Note breaking changes, required migrations, environment variable changes,
   and manual post-deploy steps.

## Write

- Group entries by change type: breaking changes first, then features, bug
  fixes, and other improvements. Omit empty groups.
- Write each entry as one line describing the user-visible effect, not the
  implementation. Link the PR number (`#123`) and the issue where one exists.
- Write for the repository's actual audience (contributors, operators, or end
  users) as evidenced by the existing changelog or release notes; match the
  established format when one exists.
- Include a deployment-notes section only when migrations, config changes, or
  manual steps apply.
- If nothing merged in the window, state that plainly.

## Publish

Route publication through the repository's mapped `delivery` capability —
its release-notes file, GitHub Release, or documented announcement channel.
Do not hardcode webhooks, chat integrations, or any transport in this
procedure; the plugin's hooks block chat-webhook posts, and the destination
is repository configuration, not workflow policy. If the repository maps no
publication target, write the notes to the changelog file the repository
already uses and report where they landed.
