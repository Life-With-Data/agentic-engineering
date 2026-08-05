// Shared test helpers (not a test file — no .test. in the name).

// Split a markdown document into its `## `-headed sections.
export function splitSections(content: string): { slug: string; block: string }[] {
  return [...content.matchAll(/^## (.+)$/gm)].map((m, i, all) => {
    const start = m.index! + m[0].length;
    const end = i + 1 < all.length ? all[i + 1].index! : content.length;
    return { slug: m[1].trim(), block: content.slice(start, end) };
  });
}

const gitEnv: NodeJS.ProcessEnv = {
  ...process.env,
  GIT_AUTHOR_NAME: "Test",
  GIT_AUTHOR_EMAIL: "test@example.com",
  GIT_COMMITTER_NAME: "Test",
  GIT_COMMITTER_EMAIL: "test@example.com",
};

export async function runGit(
  args: string[],
  cwd: string,
  env: NodeJS.ProcessEnv = gitEnv
): Promise<void> {
  const proc = Bun.spawn(["git", ...args], {
    cwd,
    stdout: "pipe",
    stderr: "pipe",
    env,
  });
  const exitCode = await proc.exited;
  const stderr = await new Response(proc.stderr).text();
  if (exitCode !== 0) {
    throw new Error(
      `git ${args.join(" ")} failed (exit ${exitCode}).\nstderr: ${stderr}`
    );
  }
}
