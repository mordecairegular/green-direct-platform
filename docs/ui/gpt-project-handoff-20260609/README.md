# GPT Project UI Review Handoff - 2026-06-09

This folder is an isolated handoff package for moving the next UI review round into a ChatGPT Project.

Current local branch: `codex/UI`

GitHub repository provided by the user:

```text
https://github.com/mordecairegular/green-direct-platform
```

Useful GitHub links:

```text
Repository:
https://github.com/mordecairegular/green-direct-platform

Branch:
https://github.com/mordecairegular/green-direct-platform/tree/codex/UI

Last committed local HEAD before this handoff refresh:
6432f15e6738397db1a5784e66ad21a6da399146
docs(ui): add ChatGPT Project handoff package

Current implemented UI/economy baseline before the docs-only handoff commit:
c93d17a9f03dbafd113d90ab229680be296250cc
feat(ui): surface price-curve workflow and landed price metrics
```

This folder has local working-copy updates for the 2026-06-09 GPT Project handoff. If ChatGPT Project cannot see the branch through the GitHub connector, upload the Markdown files from this folder manually and either push `codex/UI` later or ask GPT to inspect the default branch plus the uploaded docs. If the repository is private or newly created and the connector does not find it, run a repository import/search in ChatGPT using:

```text
repo:mordecairegular/green-direct-platform import
```

Official references:

- ChatGPT Projects: https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt
- GitHub connector: https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt
- Codex: https://help.openai.com/en/articles/11369540-codex-in-chatgpt

## Recommended ChatGPT Project Setup

Create a new Project named:

```text
Green Direct UI Review - 20260609
```

Recommended project memory setting, if shown during creation:

```text
Project-only memory
```

Reason: this UI review should stay isolated from other work and should not blend with unrelated ChatGPT context.

Upload these Markdown files from this folder:

```text
README.md
01_PROJECT_CONTEXT.md
02_UI_REVIEW_PROMPT.md
03_CODEX_RETURN_BRIEF.md
04_SOURCE_FILE_MANIFEST.md
05_SCREENSHOT_AND_RECORDING_CHECKLIST.md
```

Then paste the contents of `01_PROJECT_CONTEXT.md` into Project instructions, or keep it uploaded and paste the shorter instruction block from that file.

Start the first Project chat by pasting `02_UI_REVIEW_PROMPT.md`.

## Optional Screenshot Uploads

Current main-interface long screenshots generated for this handoff are in:

```text
docs/ui/gpt-project-handoff-20260609/screenshots-main-long-20260609/
```

Upload this first batch:

```text
01-main-long-project-launch.png
02-main-long-simulation-before-demo.png
03-main-long-simulation-after-demo.png
05-main-long-economy-after-run.png
06-main-long-recommendation.png
07-main-long-chart-overview-and-detail.png
08-main-long-export-center.png
```

Also upload `09-mobile-full-project-launch.png` and `10-mobile-full-simulation.png` if you want GPT to review narrow-screen layout issues.

If your plan has a low file limit, upload `02_UI_REVIEW_PROMPT.md`, `01_PROJECT_CONTEXT.md`, `05_SCREENSHOT_AND_RECORDING_CHECKLIST.md`, and screenshots `01`, `03`, `05`, `07`, `08` first.

## How To Bring Work Back To Codex

Ask ChatGPT Project to output a final section named:

```text
给 Codex 的具体修改任务
```

Then paste that section back into Codex together with `03_CODEX_RETURN_BRIEF.md`.

Do not ask ChatGPT Project to directly rewrite core algorithms. It should produce product/UI decisions and implementation tasks; Codex will inspect the repo, implement, test, and keep the core calculation口径 stable.
