// preload.js — context isolation bridge
// No Node APIs are exposed to the renderer; the web app talks directly to
// the FastAPI server via regular HTTP fetch() calls.
window.addEventListener('DOMContentLoaded', () => {
    // Nothing to expose — the UI at localhost:8002 handles everything.
});
