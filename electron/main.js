/**
 * electron/main.js
 * CyberArc MSP AI Outreach — Electron wrapper
 *
 * Starts the Python/FastAPI server as a child process, waits until it is
 * ready, then opens the Electron BrowserWindow.
 *
 * Key design decisions
 * ─────────────────────
 * 1. APP_DATA_DIR is set to app.getPath('userData') so the SQLite database
 *    lives in the OS user-data folder.  This means the database survives
 *    application upgrades, reinstalls, or portable-exe moves.
 *
 * 2. When packaged on Windows the bundled .venv Python is located by walking
 *    several candidate paths (Scripts/ and bin/) so the app works regardless
 *    of whether electron-builder unpacks into resources/app or resources/.
 *
 * 3. A splash/loading screen is shown while the Python server boots so the
 *    user sees feedback instead of a blank window.
 */

const { app, BrowserWindow, shell, Menu, MenuItem, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');

let SERVER_PORT = 8008;
const getServerUrl = () => `http://127.0.0.1:${SERVER_PORT}`;

// User-data directory — survives upgrades on all platforms
const USER_DATA_DIR = app.getPath('userData');   // e.g. %APPDATA%\CyberArc Outreach

let mainWindow   = null;
let splashWindow = null;
let serverProcess = null;
let startupLogs = [];
let startupExit = null;

// ─────────────────────────────────────────────────────────────────────────────
// Splash / loading window — shown while the Python server boots
// ─────────────────────────────────────────────────────────────────────────────

function showSplash() {
  splashWindow = new BrowserWindow({
    width: 400, height: 240,
    frame: false, transparent: true, alwaysOnTop: true,
    resizable: false, center: true,
    icon: path.join(__dirname, '..', 'ui', 'icon.png'),
    webPreferences: { nodeIntegration: false, contextIsolation: true },
  });
  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
  splashWindow.on('closed', () => { splashWindow = null; });
}

function closeSplash() {
  if (splashWindow) { splashWindow.close(); splashWindow = null; }
}

function resolvePythonExe(projectDir) {
  const isWin = process.platform === 'win32';

  // Candidate paths (in priority order) covering different packaging layouts
  const candidates = isWin
    ? [
      // ── Preferred: bundled-python/ has python.exe + python312.dll together ──
      // The .venv/Scripts/python.exe shim requires python312.dll from the uv
      // cache dir (e.g. %APPDATA%\uv\python\...) which doesn't exist on the
      // user's machine. bundled-python/ contains the full self-contained build.
      path.join(projectDir, 'bundled-python', 'python.exe'),
      // ── Fallback: .venv shim (works only in dev on the dev machine) ──────
      path.join(projectDir, '.venv', 'Scripts', 'python.exe'),
      path.join(projectDir, '.venv', 'Scripts', 'python3.exe'),
      path.join(process.resourcesPath, 'app', 'bundled-python', 'python.exe'),
    ]
    : [
      // ── Preferred: fully self-contained standalone Python (no symlinks) ──
      path.join(projectDir, 'bundled-python', 'bin', 'python3.12'),
      path.join(projectDir, 'bundled-python', 'bin', 'python3'),
      path.join(projectDir, 'bundled-python', 'bin', 'python'),
      // ── Fallback: .venv (works in dev-mode; may be a broken symlink when
      //    packaged — kept here so legacy AppImages still attempt it) ────────
      path.join(projectDir, '.venv', 'bin', 'python3'),
      path.join(projectDir, '.venv', 'bin', 'python'),
      path.join(process.resourcesPath, '.venv', 'bin', 'python3'),
      path.join(process.resourcesPath, '.venv', 'bin', 'python'),
    ];

  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) {
        console.log(`[Electron] Found Python at: ${p}`);
        return p;
      }
    } catch (_) {
      // path doesn't exist — try next candidate
    }
  }

  // Log all tried paths to help diagnose packaging issues
  console.error('[Electron] Python not found. Tried:', candidates);
  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Launch Python server
// ─────────────────────────────────────────────────────────────────────────────

function startServer() {
  const isPackaged = app.isPackaged;
  const projectDir = isPackaged
    ? path.join(process.resourcesPath, 'app')
    : path.join(__dirname, '..');

  const isWin = process.platform === 'win32';

  const env = Object.assign({}, process.env, {
    APP_DATA_DIR:          USER_DATA_DIR,
    PYTHONUNBUFFERED:      '1',
    PYTHONDONTWRITEBYTECODE: '1',
  });

  let cmd, args;

  if (isPackaged) {
    // ── Packaged (all platforms): use the bundled uv binary ─────────────────
    const uvBin = path.join(projectDir, 'bundled-uv', isWin ? 'uv.exe' : 'uv');

    if (!fs.existsSync(uvBin)) {
      dialog.showErrorBox(
        'Installation Corrupted',
        `A required component is missing from the installation.\n\n` +
        `Missing: bundled-uv/${isWin ? 'uv.exe' : 'uv'}\n\n` +
        `Please uninstall and re-download the latest version from our website.`
      );
      app.quit();
      return;
    }

    // Make sure the binary is executable (Linux/macOS)
    if (!isWin) {
      try { fs.chmodSync(uvBin, 0o755); } catch (_) {}
    }

    // Store the venv in the user data dir — survives app updates
    env.UV_PROJECT_ENVIRONMENT = path.join(USER_DATA_DIR, 'python-env');
    // Tell uv where to store its Python downloads (next to venv, user-owned)
    env.UV_PYTHON_DIR = path.join(USER_DATA_DIR, 'python-runtime');
    // Use managed Python — uv downloads it on first run
    env.UV_PYTHON_DOWNLOADS = 'automatic';
    // Ensure Python can always find main.py and the app/ package from projectDir
    env.PYTHONPATH = projectDir;

    cmd  = uvBin;
    args = [
      'run', '--no-dev',
      'uvicorn', 'main:app',
      '--host', '127.0.0.1',
      '--port', String(SERVER_PORT),
      '--log-level', 'warning',
    ];

  } else {
    // ── Dev mode: use system uv ──────────────────────────────────────────────
    if (!isWin) {
      const home = process.env.HOME || '';
      env.PATH = `${env.PATH}:/usr/local/bin:${home}/.local/bin:${home}/.cargo/bin`;
    }
    // Also set PYTHONPATH for dev so it always resolves correctly
    env.PYTHONPATH = projectDir;
    cmd  = isWin ? 'uv.exe' : 'uv';
    args = [
      'run', 'uvicorn', 'main:app',
      '--host', '127.0.0.1',
      '--port', String(SERVER_PORT),
      '--log-level', 'warning',
    ];
  }

  console.log(`[Electron] Starting server: ${cmd} ${args.join(' ')}`);
  console.log(`[Electron] CWD: ${projectDir}`);
  console.log(`[Electron] APP_DATA_DIR: ${USER_DATA_DIR}`);

  serverProcess = spawn(cmd, args, {
    cwd: projectDir,
    env: env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,   // no console window on Windows
  });

  serverProcess.on('error', (err) => {
    console.error(`[Electron] Failed to start server: ${err.message}`);
    dialog.showErrorBox(
      'Startup Error',
      `The application could not start the background service.\n\n` +
      `Error: ${err.message}\n\n` +
      `Please try restarting the app. If the problem persists, ` +
      `uninstall and re-download the latest version.`
    );
  });

  startupLogs = [];      // keep last lines during startup
  startupExit = null;
  const logLines = [];   // keep last lines for crash dialog
  serverProcess.stdout.on('data', d => {
    const line = `[server] ${d}`;
    process.stdout.write(line);
    logLines.push(line);
    startupLogs.push(line);
    if (logLines.length > 50) logLines.shift();
    if (startupLogs.length > 80) startupLogs.shift();
  });
  serverProcess.stderr.on('data', d => {
    const line = `[server-err] ${d}`;
    process.stderr.write(line);
    logLines.push(line);
    startupLogs.push(line);
    if (logLines.length > 50) logLines.shift();
    if (startupLogs.length > 80) startupLogs.shift();
  });

  serverProcess.on('exit', (code) => {
    console.log(`[Electron] Server exited with code ${code}`);
    startupExit = { code, logs: startupLogs.slice(-20).join('') };
    if (code !== 0 && code !== null && mainWindow) {
      dialog.showErrorBox(
        'Server Crashed',
        `The Python server stopped unexpectedly (exit code ${code}).\n\n` +
        `Last log output:\n${logLines.slice(-10).join('')}\n\n` +
        `Data directory: ${USER_DATA_DIR}`
      );
    }
    serverProcess = null;
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Poll until server ready
// ─────────────────────────────────────────────────────────────────────────────

function waitForServer(retries = 40, intervalMs = 800) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      if (startupExit && startupExit.code !== 0) {
        reject(new Error(`Server exited early (code ${startupExit.code})`));
        return;
      }
      http.get(`${getServerUrl()}/api/health`, (res) => {
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

  // Always load from the local FastAPI server — it serves ui/ as static files
  // in both dev mode and packaged production builds.
  //
  // In development, clear the HTTP cache first so that any previously-cached
  // broken JS (e.g. a file that had a SyntaxError) is never served again.
  if (!app.isPackaged) {
    mainWindow.webContents.session.clearCache().then(() => {
      mainWindow.loadURL(getServerUrl());
    });
  } else {
    mainWindow.loadURL(getServerUrl());
  }

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
    if (!url.startsWith(getServerUrl())) {
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

    if (params.dictionarySuggestions.length > 0) {
      params.dictionarySuggestions.forEach(suggestion => {
        menu.append(new MenuItem({
          label: suggestion,
          click: () => mainWindow.webContents.replaceMisspelling(suggestion)
        }));
      });
      menu.append(new MenuItem({ type: 'separator' }));
    }

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
  // Show splash immediately so users see feedback right away.
  // On first run, uv downloads Python + packages which can take 1-3 minutes.
  showSplash();

  const preferredPorts = [8008, 8009, 8010];
  let started = false;
  let lastErr = null;

  for (const port of preferredPorts) {
    SERVER_PORT = port;
    startServer();
    try {
      // First run on a fresh machine: uv downloads Python (~30 MB) then
      // installs all packages — allow up to 5 minutes (375 × 800 ms).
      await waitForServer(375, 800);
      started = true;
      break;
    } catch (err) {
      lastErr = err;
      if (serverProcess) {
        try { serverProcess.kill(); } catch (_) { }
      }
    }
  }

  if (!started) {
    closeSplash();
    const extra = startupExit && startupExit.logs
      ? `\n\nLast server logs:\n${startupExit.logs}`
      : '';
    const errMsg = lastErr ? `\nError: ${lastErr.message}\n` : '\n';
    dialog.showErrorBox(
      'Startup Failed',
      `The application could not start.\n${errMsg}` +
      `Please check that you have an internet connection on first launch\n` +
      `(the app downloads its Python runtime once on first use).\n\n` +
      `If this keeps happening, please re-download and reinstall the app.` +
      extra
    );
    app.quit();
    return;
  }

  try {
    createWindow();
    closeSplash();
  } catch (err) {
    closeSplash();
    console.error('[Electron] Could not connect to server:', err.message);
    dialog.showErrorBox(
      'Startup Failed',
      `The application could not connect to its background service.\n\n` +
      `Please try restarting the app. If the problem persists, ` +
      `re-download and reinstall the latest version.`
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
    console.log('[Electron] Killing server process…');
    serverProcess.kill();
  }
});
