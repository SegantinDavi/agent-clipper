import hashlib
import html
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import logging
import math
from pathlib import Path
import secrets
import subprocess
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, Field, StrictInt, model_validator

from clipper.core.schemas import CorteVideo
from clipper.video.pause_editing import PausePlan, PauseSettings, build_pause_plan, preview_filter

logger = logging.getLogger(__name__)


class ReviewManifest(BaseModel):
    cuts: list[CorteVideo]
    pause_plans: list[PausePlan] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_plans(self):
        if self.pause_plans:
            if len(self.pause_plans) != len(self.cuts):
                raise ValueError("Every reviewed cut must have a pause plan.")
            for cut, plan in zip(self.cuts, self.pause_plans):
                plan.validate_cut(cut.start_time, cut.end_time)
        return self


def load_review_plans(directory: str, cuts: list[CorteVideo]) -> list[PausePlan]:
    manifest = ReviewManifest.model_validate_json(
        (Path(directory) / "review.json").read_text(encoding="utf-8")
    )
    if manifest.cuts != cuts or len(manifest.pause_plans) != len(cuts):
        raise ValueError("Saved pause plans are missing or differ from the approved cuts. Restart review.")
    return manifest.pause_plans


class ApprovalDecision(BaseModel):
    approved_ids: list[StrictInt]


def save_approval_decision(directory: str | Path, decision_or_ids: ApprovalDecision | list[int]) -> Path:
    """Atomically serializes an ApprovalDecision to decision.json in the specified review directory."""
    root = Path(directory)
    if isinstance(decision_or_ids, list):
        decision = ApprovalDecision(approved_ids=decision_or_ids)
    else:
        decision = decision_or_ids
    temporary = root / "decision.partial.json"
    destination = root / "decision.json"
    temporary.write_text(decision.model_dump_json(), encoding="utf-8")
    temporary.replace(destination)
    return destination


def load_approval_decision(directory: str | Path, cut_count: int | None = None) -> list[int] | None:
    """Loads and validates decision.json from the review directory if present and valid, else returns None."""
    path = Path(directory) / "decision.json"
    if not path.exists():
        return None
    try:
        data = ApprovalDecision.model_validate_json(path.read_text(encoding="utf-8"))
        if cut_count is not None:
            return validate_approval(data.model_dump(), cut_count)
        return sorted(data.approved_ids)
    except Exception as exc:
        logger.warning("Corrupted or invalid decision.json in %s: %s", directory, exc)
        return None


def validate_approval(value: dict, cut_count: int) -> list[int]:
    decision = ApprovalDecision.model_validate(value)
    ids = decision.approved_ids
    if len(ids) != len(set(ids)) or any(index < 1 or index > cut_count for index in ids):
        raise ValueError("A seleção contém cortes inválidos ou repetidos.")
    return sorted(ids)


def prepare_review(video_path: str, cuts: list[CorteVideo], output_dir: str,
                   review_session: str = "", word_timestamps: list[dict] | None = None,
                   pause_settings: PauseSettings | None = None) -> str:
    source = Path(video_path).resolve(strict=True)
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
        capture_output=True, text=True, check=True,
    ).stdout.strip())
    for index, cut in enumerate(cuts, 1):
        if not (math.isfinite(cut.start_time) and math.isfinite(cut.end_time)
                and 0 <= cut.start_time < cut.end_time <= duration):
            raise ValueError(f"Invalid preview interval for cut {index}.")
    settings = pause_settings if pause_settings is not None else PauseSettings()
    plans = [build_pause_plan(str(source), cut.start_time, cut.end_time,
                              word_timestamps or [], settings) for cut in cuts]
    manifest = ReviewManifest(cuts=cuts, pause_plans=plans)
    metadata = manifest.model_dump_json()
    signature = f"{review_session}:{source}:{source.stat().st_size}:{source.stat().st_mtime_ns}:{metadata}"
    review_id = hashlib.sha256(signature.encode()).hexdigest()[:20]
    directory = Path(output_dir).resolve() / "reviews" / review_id
    directory.mkdir(parents=True, exist_ok=True)
    for index, (cut, plan) in enumerate(zip(cuts, plans), 1):
        destination = directory / f"preview-{index}.mp4"
        if destination.exists():
            continue
        temporary = directory / f"preview-{index}.partial.mp4"
        logger.info("Generating preview %d/%d", index, len(cuts))
        try:
            if len(plan.kept) > 1:
                graph_path = directory / f"preview-{index}.filters.txt"
                graph_path.write_text(preview_filter(plan), encoding="utf-8")
                filter_args = ["-filter_complex_script", str(graph_path), "-map", "[outv]", "-map", "[a]"]
            else:
                filter_args = ["-map", "0:v:0", "-map", "0:a:0?", "-vf",
                               "scale=w='min(640,iw)':h=-2:force_divisible_by=2"]
            result = subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(cut.start_time),
                 "-t", str(cut.end_time - cut.start_time), "-i", str(source),
                 "-filter_complex_threads", "1", *filter_args, "-r", "15",
                 "-t", str(plan.duration),
                 "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
                 "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
                 "-movflags", "+faststart", str(temporary)],
                capture_output=True, text=True,
            )
            if result.returncode:
                raise RuntimeError(f"Preview {index} failed: {result.stderr[-2000:]}")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    (directory / "review.json").write_text(metadata, encoding="utf-8")
    return str(directory)


def render_review_page(cuts: list[CorteVideo], token: str,
                       pause_plans: list[PausePlan] | None = None) -> str:
    cards = []
    for index, cut in enumerate(cuts, 1):
        duration = pause_plans[index - 1].duration if pause_plans else cut.end_time - cut.start_time
        timing = (f"Original: {cut.end_time - cut.start_time:.1f}s · Após cortes de silêncio: {duration:.1f}s"
                  if pause_plans else f"Duração: {duration:.1f}s")
        cards.append(f"""<article>
<video controls preload="metadata" src="preview-{index}.mp4"></video>
<div class="details"><span class="badge">CORTE {index} · {duration:.1f}s</span>
<h2>{html.escape(cut.title)}</h2>
<p>{html.escape(cut.description or 'Descrição indisponível neste processamento antigo.')}</p>
<p class="time">No original: {cut.start_time:.2f}s – {cut.end_time:.2f}s</p>
<p class="time">{timing}</p>
<label><input type="checkbox" name="cut_id" value="{index}"> Aprovar este corte</label></div>
</article>""")
    return """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revisar cortes · Agent Clipper</title><style>
*{box-sizing:border-box}body{margin:0;background:#10141e;color:#edf2ff;font:16px system-ui}
main{max-width:1100px;margin:auto;padding:40px 24px 150px}h1{font-size:36px;margin:12px 0}
.intro,.time{color:#a7b3c9}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:22px;margin-top:32px}
article{border:1px solid #303b50;border-radius:16px;overflow:hidden;background:#1a2232}
video{width:100%;background:#000;aspect-ratio:16/9}.details{padding:22px}h2{font-size:22px}
p{line-height:1.6}.badge{font-size:12px;color:#84dccc;letter-spacing:1px}
label{display:flex;gap:12px;align-items:center;padding:14px 0;font-weight:600;cursor:pointer}
input{width:21px;height:21px;accent-color:#6ee7c5}.actions{position:fixed;bottom:0;left:0;right:0;
background:#10141ef5;border-top:1px solid #303b50;padding:20px;display:flex;justify-content:center;gap:16px;flex-wrap:wrap}
button{border:0;border-radius:9px;background:#6ee7c5;color:#10241f;font:600 16px system-ui;padding:14px 22px;cursor:pointer}
button.secondary{background:#303b50;color:white}</style><main>
<span class="badge">AGENT CLIPPER · REVISÃO</span><h1>Escolha os cortes que vão para edição</h1>
<p class="intro">Assista aos trechos e selecione os que deseja editar. Os previews mantêm o enquadramento original;
o ritmo dos cortes de silêncio já está aplicado, quando habilitado.
O formato vertical e as legendas serão aplicados após sua confirmação.</p>
<form method="post" action="/approve"><input type="hidden" name="token" value="__TOKEN__">
<div class="grid">__CARDS__</div><div class="actions">
<button type="submit" name="action" value="approve">Confirmar seleção e editar</button>
<button class="secondary" type="submit" name="action" value="reject">Rejeitar todos</button>
</div></form></main></html>""".replace("__TOKEN__", html.escape(token, quote=True)).replace("__CARDS__", "".join(cards))


def create_review_server(directory: str, port: int = 8765) -> ThreadingHTTPServer:
    root = Path(directory).resolve(strict=True)
    manifest = ReviewManifest.model_validate_json((root / "review.json").read_text(encoding="utf-8"))
    token = secrets.token_urlsafe(32)
    page = render_review_page(manifest.cuts, token, manifest.pause_plans).encode("utf-8")
    allowed_files = {f"/preview-{index}.mp4" for index in range(1, len(manifest.cuts) + 1)}

    class ReviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(page)
            elif path in allowed_files:
                super().do_GET()
            else:
                self.send_error(404)

        def do_HEAD(self):
            if urlsplit(self.path).path not in allowed_files:
                self.send_error(404)
                return
            super().do_HEAD()

        def do_POST(self):
            if self.path != "/approve":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Invalid request size")
                form = parse_qs(self.rfile.read(length).decode("utf-8"))
                if not secrets.compare_digest(form.get("token", [""])[0], token):
                    self.send_error(403)
                    return
                action = form.get("action", [""])[0]
                if action not in ("approve", "reject"):
                    raise ValueError("Invalid action")
                ids = [] if action == "reject" else [int(value) for value in form.get("cut_id", [])]
                ids = validate_approval({"approved_ids": ids}, len(manifest.cuts))
                if action == "approve" and not ids:
                    raise ValueError("Selecione um corte ou use Rejeitar todos.")
            except (ValueError, UnicodeError):
                self.send_error(400, "Selecao invalida. Volte e selecione cortes ou rejeite todos.")
                return
            with self.server.decision_lock:
                if self.server.decision is not None:
                    self.send_error(409)
                    return
                save_approval_decision(root, ids)
                self.server.decision = ids
            message = ("Seleção salva. A edição continuará no terminal." if ids
                       else "Todos os cortes foram rejeitados. Nenhum vídeo final será gerado.")
            body = f"<!doctype html><meta charset=utf-8><p>{message}</p>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            logger.debug("Review: " + format, *args)

    from threading import Lock

    server = ThreadingHTTPServer(("127.0.0.1", port), ReviewHandler)
    server.decision = None
    server.decision_lock = Lock()
    server.timeout = 0.5
    return server


def wait_for_approval(directory: str, port: int = 8765) -> list[int]:
    root = Path(directory)
    manifest = ReviewManifest.model_validate_json((root / "review.json").read_text(encoding="utf-8"))
    saved = load_approval_decision(root, len(manifest.cuts))
    if saved is not None:
        return saved
    with create_review_server(directory, port) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"\nRevise e aprove os cortes no navegador: {url}\n"
              "O pipeline aguarda sua decisão. Ctrl+C pausa sem perder a revisão.\n", flush=True)
        while server.decision is None:
            server.handle_request()
        return server.decision
