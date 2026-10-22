# Quizwala Daily Quiz Publisher

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
amount. No immediate automatic HTTP retry or alternate model is used; bounded top-up workflow runs are supported.

The workflow first runs at 12:00 UTC / 5:30 PM IST and generates the complete
**tomorrow** edition from news available that evening. Two more runs at 8:30 PM
and 11:30 PM IST automatically retry an incomplete target. Each run resumes
the oldest unpublished target before starting a new tomorrow edition. A
successful first attempt makes later same-day runs no-ops. This leaves an
overnight buffer before the target edition's first 6:30 AM release. GitHub can
delay or skip scheduled runs, so scheduling is not a delivery SLA.

The duplicate-run guard applies to each reserved attempt, with a maximum of
three attempts per target edition. A failed or incomplete edition can be retried
through scheduled runs later the same day. Workflow dispatch can also resume it,
optionally specifying `edition_date`.
Each attempt is committed before its API call. Candidate state and raw responses
are committed by the final workflow step even when generation/validation fails.
The workflow serializes runs and checks out current main. A new date has its own
attempt budget. A complete published edition makes further reservations no-ops.

The publisher owns the generation contract, independently of Flutter. Responses
are source/schema validated, then unique questions are merged into
`state/candidates/DATE.json`. Existing candidate questions and IDs are preserved.
A public edition is written as soon as **at least one retained set has 10 unique
questions**. Complete sets publish while underfilled topics remain in candidate state for later top-ups.
The 10–15 range is a target, not an upper bound: unique extra questions survive.
The complete edition is published once; its set order, question IDs and wave
assignment are then immutable. This avoids invalidating existing app attempts.
A complete candidate can recover a failed publication without another API call.

Deduplication normalizes Unicode, case, HTML, whitespace and punctuation, then
checks token overlap and character similarity across every retained same-day
set/attempt. Only the immediately previous real edition is checked cross-day.
This catches lexical near-duplicates, not arbitrary semantic paraphrases.
Conservative similarity filtering can also reject a closely worded distinct
question. Different numerical facts are not treated as near-duplicates solely
on textual similarity. Editorial review remains useful for semantic quality.

Limits: at most three reserved attempts (including interrupted/uncertain runs),
one HTTP request each, and a 2 MB publication cap. Beyond that budget, operator
review is required; no unbounded automatic retry occurs. Invalid/truncated JSON
is retained as raw response data. The publisher also salvages individually
complete question objects from a truncated outer response; cut-off question
objects are discarded. Recovered questions still pass source, schema, and
same-day deduplication checks before merging. If the truncation prevents even a
complete question object from decoding, a later attempt starts without it.
Workflow cancellation or a failed Git push can prevent candidate persistence;
inspect/recover the available runner state before retrying in that situation.

Each Flash-Lite request uses at most 18 source excerpts / 24,000 output tokens. Generation aims for at least 3 distinct topics, normally 10–15 questions each; one complete 10-question topic is enough to publish when other topics are incomplete. Typical editions have 30–60 questions; more topics may exceed 60 without shrinking topic sets. PIB, Akashvani and BBC News RSS provide public current news without paid search grounding. Only sources dated within 72 hours are accepted. Source quote matching and schema checks reject unsupported/malformed items; this is not an independent fact check. No complete articles are republished.

All topic sets are stored together in `site/latest.json` when the candidate has at least one complete set. The publisher assigns balanced release waves at 06:30, 13:00 and 18:00 Asia/Kolkata; any remainder goes to later waves. The app uses each set's `release_at` timestamp to show upcoming topics and unlock them on device. No AI request or backend job runs at release time. Released sets remain in the saved edition until the next edition's first release at 06:30 IST; publishing tomorrow early does not remove today.

`site/latest.json` is the published feed. The app can read it through GitHub raw content; Pages supplies a readable public landing page. No Cloud Run or Cloud Scheduler job is required.

### Edition archive

Successful real publications write immutable `site/editions/YYYY-MM-DD.json`,
`site/latest.json`, and `site/history.json`. History retains eight dates before
the newest edition so publishing tomorrow early still leaves today's previous
seven dates available. The app displays seven past calendar days, plus today
and tomorrow (only after all of today's sets are live) when prepared. These
feeds are served from GitHub raw content;
Firebase and the main API backend do not store these editions.

The app loads published editions only; no bundled daily quiz sample is shipped.
