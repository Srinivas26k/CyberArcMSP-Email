/**
 * electron/main.js
 * CyberArc MSP AI Outreach — Electron wrapper
 *
 * Starts the Python/FastAPI server as a child process, waits until it is
 * ready, then opens the Electron BrowserWindow.
 */

const { app, BrowserWindow, shell, Menu, MenuItem } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const SERVER_PORT = 8002;
const SERVER_URL = `http://localhost:${SERVER_PORT}`;

let mainWindow = null;
let serverProcess = null;

// ─────────────────────────────────────────────────────────────────────────────
// Launch Python server
// ─────────────────────────────────────────────────────────────────────────────

function startServer() {
  const isPackaged = app.isPackaged;
  // In dev: V2 folder. In prod: resources/app where extraResources are extracted.
  const projectDir = isPackaged
    ? path.join(process.resourcesPath, 'app')
    : path.join(__dirname, '..');

  const env = Object.assign({}, process.env);

  // When packaged: use the bundled .venv Python directly — uv is not needed on
  // the end-user machine.  When in dev: fall back to `uv run` as before.
  let cmd, args;
  if (isPackaged) {
    cmd = process.platform === 'win32'
      ? path.join(projectDir, '.venv', 'Scripts', 'python.exe')
      : path.join(projectDir, '.venv', 'bin', 'python');
    args = [
      '-m', 'uvicorn', 'main:app',
      '--host', '127.0.0.1',
      '--port', String(SERVER_PORT),
      '--log-level', 'warning',
    ];
  } else {
    // Dev mode — uv is expected to be installed
    if (process.platform !== 'win32') {
      const home = process.env.HOME || '';
      env.PATH = `${env.PATH}:/usr/local/bin:${home}/.local/bin:${home}/.cargo/bin`;
    }
    cmd = process.platform === 'win32' ? 'uv.exe' : 'uv';
    args = [
      'run', 'uvicorn', 'main:app',
      '--host', '127.0.0.1',
      '--port', String(SERVER_PORT),
      '--log-level', 'warning',
    ];
  }

  console.log(`[Electron] Starting server: ${cmd} ${args.join(' ')}`);
  console.log(`[Electron] CWD: ${projectDir}`);

  serverProcess = spawn(cmd, args, {
    cwd: projectDir,
    env: env,
    stdio: ['ignore', 'pipe', 'pipe'],
    // Windows: don't open a console window
    windowsHide: true,
  });

  serverProcess.on('error', (err) => {
    console.error(`[Electron] Failed to start server: ${err.message}`);
    const { dialog } = require('electron');
    dialog.showErrorBox(
      'Server Start Failed',
      `Could not start the Python background server.\n\nError: ${err.message}\nPython path: ${cmd}\nWorking dir: ${projectDir}`
    );
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
    width: 1400,
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

  // Open external links in the system browser (window.open AND <a href>)
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Intercept normal <a href> link navigations to external URLs
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(SERVER_URL)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  // Same for newly created windows (e.g. target="_blank")
  mainWindow.webContents.on('new-window', (event, url) => {
    event.preventDefault();
    shell.openExternal(url);
  });

  // Add context menu (right-click) for Copy/Paste
  mainWindow.webContents.on('context-menu', (event, params) => {
    const menu = new Menu();

    // Add dictionary suggestions if misspelled
    if (params.dictionarySuggestions.length > 0) {
      params.dictionarySuggestions.forEach(suggestion => {
        menu.append(new MenuItem({
          label: suggestion,
          click: () => mainWindow.webContents.replaceMisspelling(suggestion)
        }));
      });
      menu.append(new MenuItem({ type: 'separator' }));
    }

    // Standard edit commands
    menu.append(new MenuItem({ label: 'Cut', role: 'cut', enabled: params.editFlags.canCut }));
    menu.append(new MenuItem({ label: 'Copy', role: 'copy', enabled: params.editFlags.canCopy }));
    menu.append(new MenuItem({ label: 'Paste', role: 'paste', enabled: params.editFlags.canPaste }));
    menu.append(new MenuItem({ type: 'separator' }));
    menu.append(new MenuItem({ label: 'Select All', role: 'selectAll', enabled: params.editFlags.canSelectAll }));

    menu.popup();
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
