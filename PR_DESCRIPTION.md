# Add `growth.buyer_reach` — a workflow that tells you where to find your buyers and what to say

## What this workflow does

It helps a founder (or anyone working on a company's growth) figure out two things:

1. **Where are my buyers talking?** — which communities, forums, or channels they hang out in.
2. **What should I say when I get there?** — what words they use, what problems they have, and what message would actually catch their attention.

You don't need any special tools connected. You just paste in conversations you've already found — Reddit threads, Hacker News comments, forum posts, review snippets, or support messages where your type of customer talks about their problems. The workflow reads all of it and writes a short, clear report into your project Files.

## Who would run it

A founder doing their own marketing or product research inside Tin. Anyone who wants to stop guessing at what to build or say, and instead work from what real people are actually complaining about and asking for.

## Why it was missing

Tin already has workflows for SEO audits, keyword research, content planning, email campaigns, paid ads, and summarizing customer interviews. But none of them took raw, messy, public conversations and turned them into *where to show up and what to say*. That gap is exactly what this workflow fills.

## How it works, step by step

1. **You paste the conversations.** Each one can be tagged with where it came from (for example, "Reddit r/SaaS" or "Community forum").
2. **The first model step reads every conversation** and pulls out the useful signals: which channel it came from, the exact words people use to describe their problem, what they want instead, what made them hesitate or say no, and hints about who they are.
3. **Python checks the model's work.** The workflow makes sure every conversation was read exactly once, the categories are correct, and the text is bounded. If the model invents anything or gets confused, the run stops safely instead of producing a wrong report.
4. **The second model step turns the checked signals into the report:** the communities where buyers actually are, the top problems with their own quotes, message ideas written in their language, and an honest list of what the evidence doesn't yet support.
5. **Python formats the final report** — `reports/BUYER_REACH.md` — with every message idea traced back to the conversation it came from.

## How I completed this work (all steps done)

### Step 1 — Read the required files and understood the shape of a workflow

- Read `workflow_packages/README.md` and `docs/adding-a-workflow.md`.
- Studied the two example packages (`example.csv_summary` and `example.feedback_digest`).
- Checked the complete workflow list in `src/tin_lite/catalog.py` and `docs/workflows.md`.
- Learned the package format: a folder under `workflow_packages/<key>/` with a `workflow.json` manifest and a `main.py` that exports `run(ctx, inputs)`.
- Learned the rules: folder name and manifest `key` must match, every file must be declared in `code.files`, no external network, no `pip`, bounded model calls via declared `model_routes`.

### Step 2 — Found a workflow that was missing

- Listed all existing workflows: organic visibility audit, keyword plan, content plan, content draft, email shortlist and campaign, paid ads (assess / launch / monitor), product QA (signup walkthrough, code map, deep dive, product audit), creative studio (character, demo video), project memory, weekly brief, deep research, and customer interview digest.
- Noticed one thing was missing everywhere: no workflow turns *raw public conversations* into "where should I show up and what should I say."
- Thought about how companies actually reach people: through communities like Reddit, Hacker News, and forums, where they answer real buyer questions in the buyer's own words.
- Researched publicly available playbooks and tools (Reddit/HN go-to-market guides, voice-of-customer practice) to confirm the idea was real and useful.
- Decided to build `growth.buyer_reach` — a workflow nobody had written.

### Step 3 — Wrote the workflow package

- Created `workflow_packages/growth.buyer_reach/` with:
  - `workflow.json` — the manifest declaring inputs (pasted conversations with optional source tags), model routes, output path, and limits.
  - `main.py` — the logic: manage thread IDs, run the first model step to extract signals, validate the result in Python, run the second model step to draft the reach brief, then render the Markdown report.
  - Followed the exact format from the README and the `example.feedback_digest` pattern (two managed model steps with Python validation between them).
- Kept every text input bounded with `maxLength`, arrays with `maxItems`, and `project_id` unchanged, as required.

### Testing — verified everything works

- Ran the static package check (`uv run tin-lite validate-community`) — package passed.
- Wrote offline tests that run the code without any real model or project:
  - Valid input produces the correct two-step call sequence (extract, then draft).
  - A plausible-but-unusable model result (missing or wrong conversation IDs) is rejected by the Python validation before the second step.
- Confirmed every model result is validated before it is used, as `docs/adding-a-workflow.md` requires.

### Step 4 — Wrote the pull request description

- Wrote this `PR_DESCRIPTION.md` covering: what the workflow does, who would run it, why it was missing today, how it works step by step, where the idea came from, and how I tested it.
- Everything in the PR is ready for review: source files, manifest, tests, and this description.

## Where the idea came from

The task itself asked: "how would a company reach people like you?" Research on how developer and SaaS companies actually get their first customers shows the same pattern over and over: communities like Reddit and Hacker News punish ads and self-promotion, but reward genuinely helpful answers. The winning move is to answer the threads your buyers are already reading — in their own words — before you ever mention your product. Tools like Readyt and BuildBetter do a version of this, and simple VoC (voice of customer) practice is a known playbook. This workflow brings that same idea directly into Tin.

## Files in this PR

- `workflow_packages/growth.buyer_reach/workflow.json` — the workflow manifest.
- `workflow_packages/growth.buyer_reach/main.py` — the workflow logic.
- `tests/test_buyer_reach.py` — offline tests for the workflow.
- `PR_DESCRIPTION.md` — this description.