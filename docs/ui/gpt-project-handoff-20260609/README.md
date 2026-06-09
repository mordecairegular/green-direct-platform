# GPT Project UI Review Handoff

This folder is an isolated handoff package for moving the next UI review round into a ChatGPT Project.

Current local branch: `codex/UI`

Current code baseline commit for the implemented UI/economy work:

```text
c93d17a9f03dbafd113d90ab229680be296250cc
feat(ui): surface price-curve workflow and landed price metrics
```

## GitHub Link Status

This local repository currently has no GitHub remote configured. `git remote -v` returns empty, so there is no real repository URL I can safely provide yet.

After you create or connect a GitHub repository and push this branch, use these links in ChatGPT Project:

```text
Repository:
https://github.com/<owner>/<repo>

Branch:
https://github.com/<owner>/<repo>/tree/codex/UI

Code baseline commit:
https://github.com/<owner>/<repo>/commit/c93d17a9f03dbafd113d90ab229680be296250cc
```

If the repository is private or newly created and ChatGPT does not find it through the GitHub connector, run a repository import search in ChatGPT/GitHub connector using:

```text
repo:<owner>/<repo> import
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

Upload these 5 Markdown files from this folder:

```text
README.md
01_PROJECT_CONTEXT.md
02_UI_REVIEW_PROMPT.md
03_CODEX_RETURN_BRIEF.md
04_SOURCE_FILE_MANIFEST.md
```

Then paste the contents of `01_PROJECT_CONTEXT.md` into Project instructions, or keep it uploaded and paste the shorter instruction block from that file.

Start the first Project chat by pasting `02_UI_REVIEW_PROMPT.md`.

## Optional Screenshot Uploads

If you want GPT to visually inspect the current UI, upload screenshots from:

```text
docs/ui/audit-20260606-product-design/screenshots/
```

Most useful first batch:

```text
01-welcome.png
40-streamlit-02-simulation-guardrail.png
streamlit-20260609-landed-price-cards.png
23-recommendation-after-economy.png
streamlit-20260609-chart-overview-landed-cards.png
52-streamlit-20260608-chart-detail-selector.png
25-export-after-economy.png
```

If your plan has a low file limit, upload `02_UI_REVIEW_PROMPT.md`, `01_PROJECT_CONTEXT.md`, and 2-3 screenshots first.

## How To Bring Work Back To Codex

Ask ChatGPT Project to output a final section named:

```text
给 Codex 的具体修改任务
```

Then paste that section back into Codex together with `03_CODEX_RETURN_BRIEF.md`.

Do not ask ChatGPT Project to directly rewrite core algorithms. It should produce product/UI decisions and implementation tasks; Codex will inspect the repo, implement, test, and keep the core calculation口径 stable.
