# Recall daily quizzes

Public quiz data and its generator only. No Flutter source, user material, credentials or private study history.

## Approved credit-backed generation

Generation uses Vertex AI in the owner's existing Google Cloud project, charged
against eligible promotional credits and then normal billing as authorized by the
owner. GitHub Actions and public Pages use their free public-repository offering.
No Gemini Developer API key or billing change is required.

A dedicated service account receives short-lived credentials through Workload
Identity Federation. Trust is restricted to this repository's numeric ID, owner ID
and main branch. No long-lived service-account key is stored.

Set Actions repository variable `DAILY_GENERATION_ENABLED=true` to enable, or
`false` to disable. The daily AI request is not guaranteed to be free: credits have
eligibility and expiry limits. Input/output caps bound usage, not an exact currency
amount. No automatic paid retry or alternate model is used.

The workflow uses standard Ubuntu runners in a public repository (free GitHub Actions). It targets 00:30 UTC / 06:00 IST, but GitHub can delay or skip scheduled runs. It reserves the day's attempt in Git BEFORE generation, so manual reruns cannot make another call that day. Do not remove reservation files to retry. An uncertain/failed request keeps yesterday's content; no paid fallback or automatic retry. Scheduled workflows can be disabled after 60 days of repository inactivity; check Actions if publication stops.

One Flash-Lite request, at most 18 source excerpts / 6,000 output tokens, 3–18 validated MCQs split into up to 3 topics. PIB, Akashvani and BBC News RSS provide public current news without paid search grounding. Only sources dated within 72 hours are accepted. Source quote matching and schema checks reject unsupported/malformed items; this is not an independent fact check. No complete articles are republished.

`site/latest.json` is the published feed. The app can read it through GitHub raw content; Pages supplies a readable public landing page. No Cloud Run or Cloud Scheduler job is required.
