# English Studio

Una app web local para practicar inglés de dos formas:

- **Texto → audio:** escribe una frase y escúchala con las voces en inglés de [Kokoro](https://github.com/thewh1teagle/kokoro-onnx). Elige voz estadounidense o británica y ajusta la velocidad; puedes descargar el WAV.
- **Micrófono → texto:** habla desde el navegador y lee la transcripción realizada por [Cactus Whistle](https://huggingface.co/Cactus-Compute/whistle). Permite inglés, español o detección automática; las grabaciones duran hasta 30 segundos.

## Primer uso (Linux, desde el repositorio)

Necesitas `uv`, `ffmpeg` e Internet durante la primera instalación. En Debian/Ubuntu: `sudo apt install ffmpeg`. En la carpeta de este proyecto basta con:

```bash
./start.sh
```

Este script instala las dependencias fijadas en `uv.lock`, prepara los modelos si aún no están y arranca el servidor. Abre **http://127.0.0.1:8000** en un navegador actualizado (Chrome, Firefox o similar), concede permiso al micrófono y usa cualquiera de las dos tarjetas. Para elegir otro puerto: `./start.sh --port 8080`.

La primera ejecución descarga aproximadamente 159 MB (Kokoro INT8: 114 MB, voces: 28 MB, Whistle: 17 MB), verifica sus sumas SHA-256 y los guarda en `models/`. También prepara el motor nativo de Whistle en la caché del usuario. Después, las sesiones funcionan sin conexión. La inferencia ocurre en tu equipo: las solicitudes del navegador van solo a `127.0.0.1`. La app desactiva por defecto la telemetría de `cactus-needle`.

Alternativa manual: `uv sync --locked`, `uv run whistle-web setup` y `uv run whistle-web`.

## Paquetes para distribuir

```bash
uv build
```

Esto produce un **wheel** (`.whl`) y un paquete fuente (`.tar.gz`) en `dist/`. No son ejecutables autónomos ni contienen los modelos: requieren Python, `ffmpeg` y la descarga inicial. Tras instalar el wheel con un gestor de paquetes Python, ejecuta `whistle-web setup` y `whistle-web`. El wheel usa `~/.cache/english-studio/models/`; el repositorio usa `models/`. Puedes elegir otro lugar con `WHISTLE_MODELS_DIR`.

> El audio se envía **del navegador a este servidor local**, no a un servicio de transcripción remoto. El micrófono requiere `localhost`/`127.0.0.1` o HTTPS; no basta con abrir el archivo HTML directamente. Si abres la app desde otro dispositivo, necesitarás HTTPS y una configuración adicional no incluida aquí.

## Pruebas

```bash
uv run python -m unittest discover -s tests -v
node --test tests/test_ui.cjs
```
