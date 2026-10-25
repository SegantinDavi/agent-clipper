# Speaker focus assets

The production pipeline uses these two prepared models without downloading code,
weights or media during inference:

- `face_detection_yunet.onnx`: OpenCV Zoo YuNet face detector (CPU).
- `light_asd.onnx`: Light-ASD CVPR 2023 pretrained AVA audiovisual classifier,
  exported with dynamic sequence length and batch size fixed at one (CPU).

Original repository revisions and URLs are locked in `sources.json`. SHA-256
checksums and ONNX parity results are recorded in `manifest.json`. Upstream
licenses are included in `LICENSE-YuNet` and `LICENSE-Light-ASD`.

Light-ASD attribution: Junhua Liao, Haihan Duan, Kanghui Feng, Wanbing Zhao,
Yanbing Yang and Liangyin Chen. *A Light Weight Model for Active Speaker
Detection*. CVPR 2023. https://github.com/Junhua-Liao/Light-ASD

Reproduce preparation using an isolated Python environment:

```bash
python -m venv /tmp/agent-clipper-speaker-export
/tmp/agent-clipper-speaker-export/bin/python -m pip install -r tools/requirements-speaker-export.txt
/tmp/agent-clipper-speaker-export/bin/python tools/export_speaker_models.py
```

PyTorch is required only by this preparation tool and is not imported by the
production editor. The export tool replaces the original audio encoder's
unbatched 3D pooling with equivalent 2D pooling for valid ONNX rank inference,
and compares exported outputs against the unmodified original network at two
sequence lengths. Maximum absolute error in the validated export is below 3e-6.

The classifier produces active-speaker scores, not guaranteed identity labels.
It can be uncertain during overlap, occlusions, laughter or offscreen dialogue.
