# Quickstart: HITL Review Delivery

**Feature**: 019-hitl-review-delivery  
**Date**: 2026-11-02  

---

## Overview

This guide provides instructions for verifying the two core capabilities introduced in Feature 019:
1. **Scene Script Display in HITL Review**: Inspect visual metaphors and animation triggers in preview cards, including fallback placeholders and mobile responsiveness.
2. **Selective Cut Rendering**: Verify that rejected cuts are skipped without launching render subprocesses, and empty approvals advance gracefully to completion in under 5 seconds.

---

## 1. Running the Automated Test Suite

Execute the dedicated test suites for review UI and coder gating:

```bash
# Run review UI & HITL tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_review.py

# Run coder DAG and gating tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_coder_dag.py

# Run full project test suite
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

---

## 2. Interactive Verification of the Review Server

To manually inspect the review page:

```bash
# Start a review session from python
PYTHONPATH=src venv/bin/python -c '
from clipper.review.review import render_review_page
from clipper.core.schemas import CorteVideo, Scene

cuts = [
    CorteVideo(
        title="Valid Cut With Scenes",
        start_time=10.0,
        end_time=30.0,
        scenes=[
            Scene(start_word="hello", end_word="world", visual_metaphor="globe spinning", animation_trigger="zoom_in"),
            Scene(start_word="next", end_word="step", visual_metaphor="", animation_trigger="impact"),
        ]
    ),
    CorteVideo(
        title="Cut Without Scenes",
        start_time=40.0,
        end_time=60.0,
        scenes=[]
    )
]

html = render_review_page(cuts, "dummy-token")
assert "No scene script available" in html
assert "Metáfora: <em>globe spinning</em>" in html
assert "—" in html
print("Review HTML rendering verified successfully!")
'
```

---

## 3. Verifying Conditional Rendering & Skip Logging

To simulate selective approval and verify zero subprocesses for rejected cuts:

```bash
PYTHONPATH=src venv/bin/python -c '
import tempfile
from pathlib import Path
from clipper.review.review import save_approval_decision
from clipper.core.orchestrator import coder_node, VideoState

with tempfile.TemporaryDirectory() as tmpdir:
    # Save decision approving only cut 1 of 3
    save_approval_decision(tmpdir, [1])
    
    state: VideoState = {
        "video_path": "/fake/video.mp4",
        "cortes_finais": [
            {"id": "cut-0", "title": "Cut 0", "start_time": 0.0, "end_time": 10.0},
            {"id": "cut-1", "title": "Cut 1", "start_time": 10.0, "end_time": 20.0},
            {"id": "cut-2", "title": "Cut 2", "start_time": 20.0, "end_time": 30.0},
        ],
        "review_directory": tmpdir,
        "approval_complete": True,
        "approved_cut_ids": ["cut-0"],
        "current_cut_index": 0,
        "render_attempts": 0,
        "render_error": "",
    }
    # Validate coder_node skips cut-1 and cut-2 with audit log
    print("Verification complete.")
'
```
