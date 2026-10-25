"""Select a runtime before importing inference libraries or configuration."""

import argparse
import getpass
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent Clipper with cut approval")
    parser.add_argument("--provider", choices=("gemini", "ollama"), help="LLM runtime profile")
    parser.add_argument("--model", help="Model for the selected provider")
    parser.add_argument("--url", help="YouTube video URL")
    parser.add_argument("--non-interactive", action="store_true", help="Use CLI/environment without prompts")
    parser.add_argument("--restart", action="store_true", help="Start this video's pipeline again")
    parser.add_argument("--review-port", type=int, default=8765, help="Local review page port")
    return parser


def prompt_value(label: str, default: str) -> str:
    return input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip() or default


def configure_runtime(argv=None) -> argparse.Namespace:
    args = create_parser().parse_args(argv)
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    if os.getenv("_CLIPPER_RUNTIME_SELECTED") == "1":
        return args

    provider = args.provider or os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    interactive = sys.stdin.isatty() and not args.non_interactive and not args.provider
    try:
        if interactive:
            print("\nAgent Clipper — configurações")
            print("1. Gemini API paga + Whisper GPU (CUDA/float16)")
            print("2. Ollama local + Whisper CPU (int8)")
            default_choice = "2" if provider == "ollama" else "1"
            while True:
                choice = prompt_value("Modo", default_choice)
                if choice in {"1", "2"}:
                    provider = {"1": "gemini", "2": "ollama"}[choice]
                    break
                print("Escolha 1 ou 2.")

        if provider not in {"gemini", "ollama"}:
            raise ValueError("LLM_PROVIDER must be 'gemini' or 'ollama'.")
        model_variable = "OLLAMA_MODEL" if provider == "ollama" else "GEMINI_MODEL"
        model = args.model or os.getenv(
            model_variable, "qwen2.5:14b" if provider == "ollama" else "gemini-3.6-flash"
        )
        video_url = args.url or os.getenv("YOUTUBE_URL", "")
        if interactive:
            if not args.model:
                model = prompt_value("Modelo", model)
            if not args.url:
                video_url = prompt_value("URL do YouTube", video_url)
            if provider == "gemini" and os.getenv("GEMINI_API_KEY", "").strip() in {"", "COLE_SUA_API_KEY_AQUI"}:
                os.environ["GEMINI_API_KEY"] = getpass.getpass("GEMINI_API_KEY (oculta): ").strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nConfiguração cancelada.") from None

    os.environ.update({
        "LLM_PROVIDER": provider,
        model_variable: model,
        "YOUTUBE_URL": video_url,
        "_CLIPPER_RUNTIME_SELECTED": "1",
    })
    return args
