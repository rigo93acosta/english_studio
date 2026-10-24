const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('el botón pasa de grabar a detener y vuelve a quedar disponible', async () => {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, {
        value: id === 'language' ? 'en' : '',
        disabled: false,
        textContent: '',
        listeners: {},
        attributes: {},
        classList: {
          add: (name) => classes.add(name),
          remove: (name) => classes.delete(name),
          toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
          contains: (name) => classes.has(name),
        },
        addEventListener(type, callback) { this.listeners[type] = callback; },
        setAttribute(name, value) { this.attributes[name] = value; },
      });
    }
    return elements.get(id);
  }

  let pendingStop;
  let tracksStopped = 0;
  let recording;
  class MediaRecorder {
    static isTypeSupported() { return true; }
    constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; this.listeners = {}; recording = this; }
    addEventListener(type, callback) { this.listeners[type] = callback; }
    start() { this.state = 'recording'; }
    stop() {
      this.state = 'inactive';
      this.listeners.dataavailable({ data: new Blob([new Uint8Array(300)]) });
      pendingStop = this.listeners.stop();
    }
  }

  const script = fs.readFileSync(path.join(__dirname, '../src/whistle_voz/static/app.js'), 'utf8');
  vm.runInNewContext(script, {
    document: { getElementById: element },
    window: { MediaRecorder },
    MediaRecorder,
    Blob,
    FormData,
    URL: { createObjectURL: () => 'blob:prueba', revokeObjectURL: () => {} },
    navigator: { mediaDevices: { getUserMedia: async () => ({
      getTracks: () => [{ stop: () => { tracksStopped++; } }],
    }) } },
    fetch: async (url) => ({
      ok: true,
      json: async () => url === '/api/status'
        ? { kokoro_ready: true, whistle_ready: true }
        : { text: 'Hello', language: 'en' },
    }),
    setInterval: () => 1,
    clearInterval: () => {},
  });

  const button = element('record-button');
  await button.listeners.click();
  assert.equal(recording.state, 'recording');
  assert.equal(button.disabled, false);
  assert.equal(button.attributes['aria-label'], 'Detener grabación');
  assert.equal(element('mic-zone').classList.contains('recording'), true);

  await button.listeners.click();
  await pendingStop;
  assert.equal(recording.state, 'inactive');
  assert.equal(tracksStopped, 1);
  assert.equal(button.disabled, false);
  assert.equal(button.attributes['aria-label'], 'Empezar a grabar');
  assert.equal(element('transcript').textContent, 'Hello');
});
