"""Servidor local de práctica de inglés: Kokoro (voz) y Whistle (transcripción)."""

import argparse
import hashlib
import io
import logging
import os
import subprocess
import tempfile
import threading
import urllib.request
import wave
from pathlib import Path
from typing import Literal

# Whistle no debe enviar estadísticas de uso por defecto desde esta app local.
os.environ.setdefault("NEEDLE_TELEMETRY", "0")
ROOT = Path(__file__).resolve().parents[2]
SOURCE_CHECKOUT = (ROOT / "pyproject.toml").is_file() and (ROOT / "src" / "whistle_voz").is_dir()
CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache").expanduser()
DEFAULT_MODELS = ROOT / "models" if SOURCE_CHECKOUT else CACHE_ROOT / "english-studio" / "models"
MODELS = Path(os.environ.get("WHISTLE_MODELS_DIR", DEFAULT_MODELS)).expanduser()
MODEL = MODELS / "kokoro-v1.0.int8.onnx"
VOICES = MODELS / "voices-v1.0.bin"
WHISTLE = MODELS / "whistle.cact"
# Con pesos explícitos, la librería no registra descargas en cada arranque.
os.environ.setdefault("NEEDLE_WHISTLE_WEIGHTS", str(WHISTLE))

import needle
import soundfile as sf
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from kokoro_onnx import Kokoro
from pydantic import BaseModel, Field


STATIC = Path(__file__).resolve().parent / "static"
BASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
CHECKSUMS = {
    MODEL.name: "ae315a79b623f244700e4afb9246c46a26066782e049ba174bf3ba433970ee9c",
    VOICES.name: "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
    WHISTLE.name: "b6e02f048568ac5d01a2042556c658061e699acbc0aa2a1439f52f3d461dffeb",
}
MAX_AUDIO_BYTES = 12 * 1024 * 1024
MAX_SECONDS = 30
_tts: Kokoro | None = None
_tts_lock = threading.Lock()
logger = logging.getLogger(__name__)

app = FastAPI(title="English Studio", docs_url=None, redoc_url=None)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    voice: Literal["af_heart", "am_michael", "bf_emma", "bm_george"] = "af_heart"
    speed: float = Field(default=1.0, ge=0.7, le=1.2)


def download_models() -> None:
    """Descarga archivos oficiales y verifica sus SHA-256 antes de utilizarlos."""
    MODELS.mkdir(parents=True, exist_ok=True)
    for path in (MODEL, VOICES, WHISTLE):
        expected = CHECKSUMS[path.name]
        if path.is_file() and _sha256(path) == expected:
            print(f"Ya está descargado: {path.name}")
            continue
        print(f"Descargando {path.name}...", flush=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=MODELS, delete=False) as target:
                temporary = Path(target.name)
                url = ("https://huggingface.co/Cactus-Compute/whistle/resolve/main/whistle.cact"
                       if path == WHISTLE else BASE_URL + path.name)
                request = urllib.request.Request(url, headers={"User-Agent": "whistle-web/0.1"})
                with urllib.request.urlopen(request, timeout=90) as source:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
            if _sha256(temporary) != expected:
                raise ValueError(f"La verificación SHA-256 falló para {path.name}")
            temporary.replace(path)
            print(f"Listo: {path.name}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    # Descarga el motor nativo en la instalación, no durante el primer uso offline.
    print("Preparando el motor local de Whistle...", flush=True)
    needle.Whistle(weights=str(WHISTLE))
    print("Modelos listos para usar sin conexión.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _kokoro() -> Kokoro:
    global _tts
    if not MODEL.is_file() or not VOICES.is_file():
        raise HTTPException(503, "Faltan los modelos de Kokoro. Ejecuta: uv run whistle-web setup")
    if _tts is None:
        _tts = Kokoro(str(MODEL), str(VOICES))
    return _tts


def _whistle_ready() -> bool:
    return Path(os.environ["NEEDLE_WHISTLE_WEIGHTS"]).is_file()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/app.css")
def css() -> FileResponse:
    return FileResponse(STATIC / "app.css", media_type="text/css")


@app.get("/app.js")
def js() -> FileResponse:
    return FileResponse(STATIC / "app.js", media_type="application/javascript")


@app.get("/api/status")
def status() -> dict[str, bool]:
    return {"kokoro_ready": MODEL.is_file() and VOICES.is_file(), "whistle_ready": _whistle_ready()}


@app.post("/api/speak")
def speak(request: SpeechRequest) -> Response:
    if not request.text.strip():
        raise HTTPException(400, "Escribe una frase antes de generar el audio.")
    # La sesión de ONNX se comparte; se serializa el uso para evitar carreras.
    try:
        with _tts_lock:
            samples, sample_rate = _kokoro().create(
                request.text.strip(), voice=request.voice, speed=request.speed,
                lang="en-gb" if request.voice.startswith("b") else "en-us",
            )
        result = io.BytesIO()
        sf.write(result, samples, sample_rate, format="WAV", subtype="PCM_16")
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("No se pudo generar audio con Kokoro")
        raise HTTPException(503, f"Kokoro no pudo generar el audio: {error}") from error
    return Response(result.getvalue(), media_type="audio/wav", headers={
        "Content-Disposition": 'attachment; filename="english-practice.wav"',
        "Cache-Control": "no-store",
    })


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), language: Literal["en", "es", "auto"] = "en") -> dict[str, str]:
    try:
        data = await audio.read(MAX_AUDIO_BYTES + 1)
    finally:
        await audio.close()
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(400, "La grabación está vacía o supera los 12 MB.")
    if not _whistle_ready():
        raise HTTPException(503, "Falta el modelo Whistle. Ejecuta: uv run whistle-web setup")

    # MediaRecorder produce WebM/Opus, Ogg o MP4 según el navegador.
    # Whistle recibe un WAV PCM mono a 16 kHz, independiente del formato original.
    try:
        with tempfile.TemporaryDirectory() as directory:
            wav = Path(directory) / "microphone.wav"
            converted = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                input=data, capture_output=True, timeout=40, check=False,
            )
            if converted.returncode != 0 or not wav.is_file():
                raise HTTPException(400, "El navegador envió audio que no se pudo leer.")
            with wave.open(str(wav), "rb") as reader:
                duration = reader.getnframes() / reader.getframerate()
            if duration < 0.15 or duration > MAX_SECONDS + 1:
                raise HTTPException(400, "Graba entre 0,15 y 30 segundos de voz.")
            result = needle.transcribe(str(wav), **({} if language == "auto" else {"language": language}))
    except HTTPException:
        raise
    except FileNotFoundError as error:
        raise HTTPException(503, "Falta ffmpeg. Instálalo y reinicia el servidor.") from error
    except subprocess.TimeoutExpired as error:
        raise HTTPException(408, "Se agotó el tiempo de procesamiento del audio.") from error
    except Exception as error:
        logger.exception("Falló la transcripción de Whistle")
        raise HTTPException(503, f"No se pudo transcribir. Verifica la conexión inicial y vuelve a intentarlo: {error}") from error
    return {"text": result.get("text") or "", "language": result.get("language") or language}


def main() -> None:
    parser = argparse.ArgumentParser(description="App web local Kokoro + Whistle")
    parser.add_argument("action", nargs="?", choices=["serve", "setup"], default="serve")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.action == "setup":
        download_models()
    else:
        uvicorn.run(app, host="127.0.0.1", port=args.port)
