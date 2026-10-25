"""Prepare licensed speaker models once, outside the production environment."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "agent-clipper-model-preparation"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=root / "assets" / "speaker_focus")
    parser.add_argument("--build", type=Path, default=root / "output" / "asd_model_build")
    args = parser.parse_args()
    args.build.mkdir(parents=True, exist_ok=True)
    sources = json.loads((args.assets / "sources.json").read_text(encoding="utf-8"))
    for source in sources.values():
        if "revision" not in source:
            source["revision"] = json.loads(fetch(source["revision_url"]))["sha"]
    (args.assets / "sources.json").write_text(
        json.dumps(sources, indent=2) + "\n", encoding="utf-8",
    )

    upstream = sources["light_asd"]
    base = upstream["raw_base"].format(revision=upstream["revision"])
    downloaded = {}
    for name in [*upstream["sources"], upstream["weight"]]:
        destination = args.build / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = fetch(base + name)
        destination.write_bytes(content)
        downloaded[name] = hashlib.sha256(content).hexdigest()
    (args.assets / "LICENSE-Light-ASD").write_bytes(fetch(base + "LICENSE"))
    detector = sources["yunet"]
    (args.assets / "face_detection_yunet.onnx").write_bytes(
        fetch(detector["model_url"].format(revision=detector["revision"]))
    )
    (args.assets / "LICENSE-YuNet").write_bytes(
        fetch(detector["license_url"].format(revision=detector["revision"]))
    )

    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch

    sys.path.insert(0, str(args.build))
    from model.Model import ASD_Model

    torch.set_num_threads(2)
    torch.manual_seed(0)

    class ExportModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = ASD_Model()
            self.classifier = torch.nn.Linear(128, 2)

        def forward(self, audio, faces):
            features, _ = self.encoder(audio, faces)
            return self.classifier(features)[:, 1]

    model = ExportModel().eval()
    weights = torch.load(args.build / upstream["weight"], map_location="cpu", weights_only=True)
    weights = {key.removeprefix("module."): value for key, value in weights.items()}
    model.encoder.load_state_dict({
        key.removeprefix("model."): value
        for key, value in weights.items() if key.startswith("model.")
    })
    model.classifier.load_state_dict({
        key.removeprefix("lossAV.FC."): value
        for key, value in weights.items() if key.startswith("lossAV.FC.")
    })
    reference = copy.deepcopy(model).eval()
    for name in ("pool1", "pool2"):
        original_pool = getattr(model.encoder.audioEncoder, name)
        if original_pool.kernel_size[0] != 1 or original_pool.stride[0] != 1:
            raise RuntimeError("Unexpected upstream audio pooling configuration.")
        # The source applies unbatched MaxPool3d to rank-4 audio; equivalent 2D pooling exports correctly.
        setattr(model.encoder.audioEncoder, name, torch.nn.MaxPool2d(
            kernel_size=original_pool.kernel_size[1:], stride=original_pool.stride[1:],
            padding=original_pool.padding[1:], dilation=original_pool.dilation,
            ceil_mode=original_pool.ceil_mode,
        ))
    audio = torch.randn(1, 100, 13)
    faces = torch.rand(1, 25, 112, 112) * 255
    destination = args.assets / "light_asd.onnx"
    with torch.inference_mode():
        torch.onnx.export(
            model, (audio, faces), str(destination), opset_version=17, dynamo=False,
            input_names=["audio", "faces"], output_names=["scores"],
            dynamic_axes={"audio": {1: "audio_frames"}, "faces": {1: "video_frames"},
                          "scores": {0: "video_frames"}},
        )
    graph = onnx.load(str(destination))
    onnx.checker.check_model(graph)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(destination), options, providers=["CPUExecutionProvider"])
    differences = []
    for length in (25, 50):
        audio = torch.randn(1, length * 4, 13)
        faces = torch.rand(1, length, 112, 112) * 255
        with torch.inference_mode():
            expected = reference(audio, faces).numpy()
        actual = session.run(None, {"audio": audio.numpy(), "faces": faces.numpy()})[0]
        np.testing.assert_allclose(actual, expected, rtol=1e-3, atol=1e-3)
        differences.append(float(np.max(np.abs(actual - expected))))
    manifest = {
        "source_files_sha256": downloaded, "onnx_parity_max_errors": differences,
        "torch_export_version": torch.__version__,
        "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in args.assets.glob("*.onnx")},
    }
    (args.assets / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
