# Storage & Durability Contract: Review & Decision Persistence

**Feature**: `010-manual-review-langgraph-integration`  
**Date**: 2026-10-28  
**Scope**: File storage contracts for manifests, previews, atomic decision records, and SQLite state.

---

## 1. Directory Structure

```text
/app/output/
├── estado.db                    # SQLite checkpointer database
├── downloads/                   # Downloaded raw videos
├── reviews/
│   └── <review_id>/             # Unique review directory
│       ├── review.json          # Review manifest (cuts & pause plans)
│       ├── preview-1.mp4        # Rendered preview clips
│       ├── preview-1.filters.txt
│       ├── preview-2.mp4
│       ├── decision.partial.json # Ephemeral write buffer
│       └── decision.json        # Committed human decision record
└── <final_cut>.mp4              # Exported vertical videos
```

---

## 2. Review Manifest (`review.json`)

### File Path
`{review_directory}/review.json`

### Serialization Contract
UTF-8 encoded JSON string matching `ReviewManifest`:
```json
{
  "cuts": [
    {
      "start_time": 0.0,
      "end_time": 30.0,
      "title": "Clip Title",
      "description": "Short explanation"
    }
  ],
  "pause_plans": [
    {
      "source_start": 0.0,
      "source_end": 30.0,
      "duration": 28.5,
      "kept": [[0.0, 15.0], [16.5, 30.0]],
      "removals": [[15.0, 16.5]]
    }
  ]
}
```

---

## 3. Decision Record (`decision.json`)

### File Path
`{review_directory}/decision.json`

### Atomic Write Protocol
To prevent corrupted or partially written JSON during unexpected process termination (SIGKILL / OOM):
1. Write payload to `{review_directory}/decision.partial.json`.
2. Flush and close file handle.
3. Call `Path.replace()` to atomically move `.partial.json` to `decision.json`.
4. Ensure `.partial.json` does not exist after commit.

### Schema
```json
{
  "approved_ids": [1, 2]
}
```

### Invalidation & Cleanup Rules
- When the orchestrator executes with `--restart`:
  - Checkpoint records for `thread_id` in `estado.db` are deleted.
  - A new `review_session` UUID is generated.
  - Prior `decision.json` files from earlier review directories are never consulted or reused.
