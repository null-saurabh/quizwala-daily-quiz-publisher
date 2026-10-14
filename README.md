# Recall daily quizzes

Public quiz data and its generator only. No Flutter source, user material, credentials or private study history.

## Free-only setup

1. Create a Gemini Developer API key in an AI Studio project **with billing disabled**. Free quotas may change; requests must fail on exhaustion rather than charge. Public news excerpts are sent to Google's free API and may be used to improve its products.
2. In this repository's Settings → Secrets and variables → Actions, add **GEMINI_FREE_API_KEY** as a secret. Never commit the key.
3. Add the Actions repository variable **FREE_TIER_CONFIRMED** = **true** only after confirming that project's billing is disabled.
4. Run the Daily current affairs workflow once, or wait for 06:00 IST. No AI request happens before those two settings exist.

The workflow uses standard Ubuntu runners in a public repository (free GitHub Actions). It targets 00:30 UTC / 06:00 IST, but GitHub can delay or skip scheduled runs. It reserves the day's attempt in Git BEFORE generation, so manual reruns cannot make another call that day. Do not remove reservation files to retry. An uncertain/failed request keeps yesterday's content; no paid fallback or automatic retry. Scheduled workflows can be disabled after 60 days of repository inactivity; check Actions if publication stops.

One Flash-Lite request, at most 18 source excerpts / 6,000 output tokens, 3–18 validated MCQs split into up to 3 topics. PIB and Akashvani RSS provide public current news without paid search grounding. Only sources dated within 72 hours are accepted. Source quote matching and schema checks reject unsupported/malformed items; this is not an independent fact check. No complete articles are republished.

`site/latest.json` is the published feed. The app can read it through GitHub raw content; Pages supplies a readable public landing page. No Cloud Run or Cloud Scheduler job is required.
