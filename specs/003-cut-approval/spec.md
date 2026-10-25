# SDD: Review and approve cuts before editing

## Scope

Add a mandatory human review between extraction and final editing. The user has already waived the local-only AGENTS workflow constraints; this design records the implementation without requiring a new approval workflow for development.

## Behavior

- Extract a short, factual topic description alongside each title and interval.
- Generate lightweight, unedited MP4 previews with FFmpeg, one at a time. Keep the source framing and audio; final cropping and captions happen only after approval.
- Serve a Portuguese review page on localhost using Python's standard library. Each card shows title, description, interval, duration, a video player, and a selection checkbox.
- Start with no selected cuts. Require an explicit submission; support rejecting all candidates.
- Persist previews and decisions under output/reviews. Use a content-based review identifier to avoid stale decisions for changed candidates or media.
- Pause LangGraph using interrupt with SqliteSaver; resume with Command only after valid approval. Store only serializable metadata in the state.
- The editor refuses to run without approval and receives only selected cuts. An empty selection generates no final videos.
- Re-running the same URL resumes pending work. Completed work requires --restart to run again. Namespace new checkpoints to prevent historical checkpoints from bypassing review.

## Boundaries

No cloud UI, telemetry, additional LLM, or new web framework. Bind only to 127.0.0.1. Serve only preview assets, escape generated text, and validate submissions with a per-session token. Do not expose API credentials or the project directory.

## Validation

Test actual FFmpeg preview generation, escaped page content, invalid decisions, localhost approval persistence, mandatory editor gating, selection/rejection, and SQLite restart/resume without repeating upstream nodes. Run existing regression tests with mocked LLM calls.
