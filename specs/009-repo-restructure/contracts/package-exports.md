# Contract: Package Exports & Symbol Pathways

**Feature Branch**: `009-repo-restructure`  
**Date**: 2026-10-27  
**Spec**: [spec.md](../spec.md)  

## Export Specifications

### 1. `clipper.core`

#### `clipper.core.schemas`
```python
from clipper.core.schemas import (
    CorteVideo,        # Pydantic BaseModel for individual cuts
    CortesResponse     # Pydantic BaseModel containing cuts list
)
```

#### `clipper.core.prompts`
```python
from clipper.core.prompts import (
    ChatMessage,
    THINKER_SYSTEM_PROMPT,
    EXTRACTOR_SYSTEM_PROMPT_TEMPLATE,
    EXTRACTOR_FEW_SHOT_EXAMPLES
)
```

#### `clipper.core.ingestion`
```python
from clipper.core.ingestion import (
    download_video,
    transcribe_audio_chunk,
    download_video_and_transcript
)
```

#### `clipper.core.node_0`
```python
from clipper.core.node_0 import (
    node_0_preventive_slicing,
    get_silence_points
)
```

#### `clipper.core.orchestrator`
```python
from clipper.core.orchestrator import (
    VideoState,
    create_graph,
    run_with_review,
    checkpoint_thread_id,
    main
)
```

---

### 2. `clipper.video`

#### `clipper.video.editor`
```python
from clipper.video.editor import (
    cut_and_format_video,
    group_caption_words,
    load_caption_font,
    remove_caption_punctuation,
    create_caption_clip,
    position_caption_clip
)
```

#### `clipper.video.pause_editing`
```python
from clipper.video.pause_editing import (
    PausePlan,
    PauseSettings,
    build_pause_plan,
    identity_plan,
    preview_filter,
    remap_word_groups
)
```

#### `clipper.video.speaker_focus`
```python
from clipper.video.speaker_focus import (
    FramingPlan,
    FaceTracker,
    SpeakerSelector,
    SpeakerModels,
    face_crop,
    build_framing_plan,
    apply_framing_plan
)
```

---

### 3. `clipper.review`

#### `clipper.review.review`
```python
from clipper.review.review import (
    ReviewManifest,
    load_review_plans,
    prepare_review,
    wait_for_approval,
    validate_approval,
    render_review_page
)
```

---

### 4. `clipper.runtime`

#### `clipper.runtime.config`
```python
from clipper.runtime.config import (
    PROJECT_ROOT,
    OUTPUT_DIR,
    YOUTUBE_URL,
    LLM_PROVIDER,
    MODEL_NAME,
    OLLAMA_BASE_URL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    SILENCE_CUT_ENABLED,
    SILENCE_MIN_PAUSE,
    SILENCE_KEEP_PAUSE,
    SILENCE_SPEECH_PADDING,
    SILENCE_THRESHOLD_DB,
    SPEAKER_FOCUS_ENABLED
)
```

#### `clipper.runtime.cuda_runtime`
```python
from clipper.runtime.cuda_runtime import (
    cuda_library_directories,
    prepare_cuda_environment,
    validate_cuda_runtime
)
```

#### `clipper.runtime.runtime_options`
```python
from clipper.runtime.runtime_options import (
    create_parser,
    prompt_value,
    configure_runtime
)
```
