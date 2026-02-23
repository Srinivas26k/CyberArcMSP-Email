/**
 * electron/main.js
 * CyberArc MSP AI Outreach — Electron wrapper
 *
 * Starts the Python/FastAPI server as a child process, waits until it is
 * ready, then opens the Electron BrowserWindow.
 */

const { app, BrowserWindow, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const SERVER_PORT = 8002;
const SERVER_URL  = `http://localhost:${SERVER_PORT}`;

let mainWindow = null;
let serverProcess = null;

// ─────────────────────────────────────────────────────────────────────────────
// Launch Python server
// ─────────────────────────────────────────────────────────────────────────────

function startServer() {
  const projectDir = path.join(__dirname, '..');

  // Use `uv run` so it picks up the virtual-env automatically
  const cmd  = process.platform === 'win32' ? 'uv.exe' : 'uv';
  const args = [
    'run', 'uvicorn', 'main:app',
    '--host', '127.0.0.1',
    '--port', String(SERVER_PORT),
    '--log-level', 'warning',
  ];

  console.log(`[Electron] Starting server: ${cmd} ${args.join(' ')}`);

  serverProcess = spawn(cmd, args, {
    cwd: projectDir,
    stdio: ['ignore', 'pipe', 'pipe'],
    // Windows: don't open a console window
    windowsHide: true,
  });

  serverProcess.stdout.on('data', d => process.stdout.write(`[server] ${d}`));
  serverProcess.stderr.on('data', d => process.stderr.write(`[server] ${d}`));

  serverProcess.on('exit', (code) => {
    console.log(`[Electron] Server exited with code ${code}`);
    serverProcess = null;
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Poll until server ready
// ─────────────────────────────────────────────────────────────────────────────

function waitForServer(retries = 30, intervalMs = 1000) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      http.get(`${SERVER_URL}/api/health`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
      }).on('error', retry);
    };
    const retry = () => {
      attempts++;
      if (attempts >= retries) {
        reject(new Error('Server did not start in time'));
      } else {
        setTimeout(check, intervalMs);
      }
    };
    check();
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Create window
// ─────────────────────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width:  1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'CyberArc MSP — AI Outreach',
    icon: path.join(__dirname, '..', 'ui', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
    backgroundColor: '#f8fafc',
  });

  mainWindow.loadURL(SERVER_URL);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
  });

  // Open external links in the system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// App lifecycle
// ─────────────────────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  startServer();
  try {
    await waitForServer(40, 800);   // up to ~32 s
    createWindow();
  } catch (err) {
    console.error('[Electron] Could not connect to server:', err.message);
    // Show a basic error dialog
    const { dialog } = require('electron');
    dialog.showErrorBox(
      'Startup failed',
      'The Python server could not start.\n\nMake sure Python and uv are installed:\n  pip install uv\n\nThen try launching again.',
    );
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});

// Kill server on quit
app.on('before-quit', () => {
  if (serverProcess) {
    console.log('[Electron] Killing server process...');
    serverProcess.kill();
  }
});
