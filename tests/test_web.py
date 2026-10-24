import io
import re
import shutil
import subprocess
import tempfile
import unittest
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from whistle_voz import web


client = TestClient(web.app)


def sample_wav() -> bytes:
    data = io.BytesIO()
    with wave.open(data, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\0\0" * 16000)
    return data.getvalue()


class FakeKokoro:
    def create(self, text, voice, speed, lang):
        assert (text, voice, speed, lang) == ("Hello!", "bf_emma", 0.8, "en-gb")
        return np.zeros(2400, dtype=np.float32), 24000


class WebTests(unittest.TestCase):
    def test_home_and_assets(self):
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("English Studio", page.text)
        self.assertIn('<svg class="hero-illustration"', page.text)
        self.assertNotIn('class="hero-actions"', page.text)
        self.assertEqual(client.get("/app.css").status_code, 200)
        self.assertEqual(client.get("/app.js").status_code, 200)
        illustration = re.search(r'<svg class="hero-illustration".*?</svg>', page.text, re.DOTALL)
        self.assertIsNotNone(illustration)
        self.assertTrue(ET.fromstring(illustration.group()).tag.endswith("svg"))

    def test_tts_uses_selected_accent_and_returns_wav(self):
        with patch.object(web, "_kokoro", return_value=FakeKokoro()):
            response = client.post("/api/speak", json={"text": "Hello!", "voice": "bf_emma", "speed": 0.8})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        with wave.open(io.BytesIO(response.content)) as reader:
            self.assertEqual(reader.getframerate(), 24000)

    def test_tts_requires_models(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(web, "MODEL", Path(directory) / "missing.onnx"):
                self.assertEqual(client.post("/api/speak", json={"text": "Hello"}).status_code, 503)

    def test_audio_is_converted_and_transcribed(self):
        with patch.object(web, "_whistle_ready", return_value=True), patch.object(
            web.needle, "transcribe", return_value={"text": "hello there", "language": "en"}
        ) as transcribe:
            response = client.post("/api/transcribe?language=en", files={"audio": ("clip.wav", sample_wav(), "audio/wav")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"text": "hello there", "language": "en"})
        self.assertEqual(transcribe.call_args.kwargs, {"language": "en"})

    def test_bad_audio_is_rejected(self):
        response = client.post("/api/transcribe", files={"audio": ("bad.webm", b"not audio", "audio/webm")})
        self.assertEqual(response.status_code, 400)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg no está instalado")
    def test_browser_webm_audio_is_accepted(self):
        converted = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "wav", "-i", "pipe:0",
             "-c:a", "libopus", "-f", "webm", "pipe:1"],
            input=sample_wav(), capture_output=True, check=True,
        )
        with patch.object(web, "_whistle_ready", return_value=True), patch.object(
            web.needle, "transcribe", return_value={"text": "hi", "language": "en"}
        ):
            response = client.post("/api/transcribe", files={
                "audio": ("browser.webm", converted.stdout, "audio/webm"),
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "hi")


if __name__ == "__main__":
    unittest.main()
