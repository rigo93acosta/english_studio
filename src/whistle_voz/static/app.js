const $ = (id) => document.getElementById(id);
let generatedUrl = null;
let recordedUrl = null;
let recorder = null;
let stream = null;
let timerId = null;
let startedAt = 0;

function setStatus(id, message, error = false) {
  const element = $(id);
  element.textContent = message;
  element.classList.toggle("error", error);
}

async function apiError(response) {
  try {
    const data = await response.json();
    return typeof data.detail === "string" ? data.detail : "No se pudo completar la solicitud.";
  } catch {
    return `Error del servidor (${response.status}).`;
  }
}

$("text").addEventListener("input", () => { $("text-length").textContent = $("text").value.length; });
$("text-length").textContent = $("text").value.length;
$("speed").addEventListener("input", () => { $("speed-value").textContent = `${Number($("speed").value).toFixed(2).replace(/0$/, "")}×`; });

$("speak-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (!text) { setStatus("speak-status", "Escribe una frase en inglés.", true); return; }
  $("speak-button").disabled = true;
  setStatus("speak-status", "Preparando la voz… La primera vez puede tardar un poco.");
  try {
    const response = await fetch("/api/speak", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: $("voice").value, speed: Number($("speed").value) })
    });
    if (!response.ok) throw new Error(await apiError(response));
    const blob = await response.blob();
    if (generatedUrl) URL.revokeObjectURL(generatedUrl);
    generatedUrl = URL.createObjectURL(blob);
    $("generated-audio").src = generatedUrl;
    $("download-link").href = generatedUrl;
    $("speak-result").hidden = false;
    setStatus("speak-status", "Audio generado. Dale al play para escucharlo.");
  } catch (error) {
    setStatus("speak-status", error.message, true);
  } finally {
    $("speak-button").disabled = false;
  }
});

function updateTimer() {
  const seconds = Math.floor((Date.now() - startedAt) / 1000);
  $("timer").textContent = `00:${String(Math.min(seconds, 30)).padStart(2, "0")}`;
  if (seconds >= 30) stopRecording();
}

function stopRecording() {
  if (recorder?.state === "recording") recorder.stop();
  clearInterval(timerId);
  $("mic-zone").classList.remove("recording");
  $("record-button").disabled = true;
  $("record-button").setAttribute("aria-label", "Procesando grabación");
  $("mic-title").textContent = "Procesando tu voz…";
  setStatus("listen-status", "Convirtiendo y transcribiendo el audio…");
}

async function submitRecording(blob) {
  if (blob.size < 100) throw new Error("La grabación está vacía. Inténtalo de nuevo.");
  if (recordedUrl) URL.revokeObjectURL(recordedUrl);
  recordedUrl = URL.createObjectURL(blob);
  $("recorded-audio").src = recordedUrl;
  const form = new FormData();
  form.append("audio", blob, "recording.webm");
  const language = encodeURIComponent($("language").value);
  const response = await fetch(`/api/transcribe?language=${language}`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await apiError(response));
  const result = await response.json();
  $("transcript").textContent = result.text || "No se detectó voz. Prueba a hablar más cerca del micrófono.";
  $("listen-result").hidden = false;
  setStatus("listen-status", "Transcripción lista. Puedes volver a grabar cuando quieras.");
}

$("record-button").addEventListener("click", async () => {
  if (recorder?.state === "recording") { stopRecording(); return; }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setStatus("listen-status", "Este navegador no permite grabar audio. Abre la app en localhost con un navegador actualizado.", true);
    return;
  }
  $("record-button").disabled = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const options = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"]
      .find((format) => MediaRecorder.isTypeSupported(format));
    recorder = new MediaRecorder(stream, options ? { mimeType: options } : undefined);
    const chunks = [];
    recorder.addEventListener("dataavailable", (event) => { if (event.data.size) chunks.push(event.data); });
    recorder.addEventListener("stop", async () => {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
      try { await submitRecording(new Blob(chunks, { type: recorder.mimeType })); }
      catch (error) { setStatus("listen-status", error.message, true); }
      finally {
        $("record-button").disabled = false;
        $("record-button").setAttribute("aria-label", "Empezar a grabar");
        $("mic-title").textContent = "Pulsa para comenzar";
      }
    }, { once: true });
    recorder.start();
    startedAt = Date.now();
    $("timer").textContent = "00:00";
    timerId = setInterval(updateTimer, 250);
    $("mic-zone").classList.add("recording");
    $("mic-title").textContent = "Te estamos escuchando";
    $("record-button").setAttribute("aria-label", "Detener grabación");
    $("record-button").disabled = false;
    setStatus("listen-status", "Habla con naturalidad. Pulsa el botón para terminar.");
  } catch (error) {
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    $("record-button").disabled = false;
    setStatus("listen-status", `No se pudo activar el micrófono: ${error.message}`, true);
  }
});

$("copy-button").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("transcript").textContent); setStatus("listen-status", "Texto copiado."); }
  catch { setStatus("listen-status", "No se pudo copiar el texto desde el navegador.", true); }
});

fetch("/api/status").then((response) => response.json()).then((data) => {
  if (!data.kokoro_ready) setStatus("speak-status", "Antes del primer uso, ejecuta en la terminal: uv run whistle-web setup");
  if (!data.whistle_ready) setStatus("listen-status", "Antes del primer uso, ejecuta en la terminal: uv run whistle-web setup");
}).catch(() => {});
