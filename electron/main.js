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

let mainWindow = null;
let serverProcess = null;
let startupLogs = [];
let startupExit = null;

// ─────────────────────────────────────────────────────────────────────────────
// Resolve Python executable inside the bundled runtime.
//
// On Windows the .venv/Scripts/python.exe produced by uv is a real PE32
// binary, so we check it directly.
//
// On Linux/macOS the .venv/bin/python entries are symlinks that point to the
// CI-runner's uv-managed Python path — a path that does NOT exist on the
// user's machine.  The build step therefore copies the entire python-build-
// standalone installation into bundled-python/ and merges .venv site-packages
// into it.  We prefer bundled-python/ first, and fall back to .venv for
// dev-mode or legacy builds.
// ─────────────────────────────────────────────────────────────────────────────

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

  const env = Object.assign({}, process.env, {
    // Tell database.py where to store the SQLite file
    APP_DATA_DIR: USER_DATA_DIR,
    // Prevent Python from buffering stdout/stderr (important for log capture)
    PYTHONUNBUFFERED: '1',
    // Avoid Python from looking for .pyc in read-only bundle directories
    PYTHONDONTWRITEBYTECODE: '1',
  });

  let cmd, args;

  if (isPackaged) {
    const pythonExe = resolvePythonExe(projectDir);
    if (!pythonExe) {
      dialog.showErrorBox(
        'Python Not Found',
        `The bundled Python interpreter could not be located.\n\n` +
        `Looked inside: ${path.join(projectDir, 'bundled-python')} (preferred)\n` +
        `         and: ${path.join(projectDir, '.venv')}\n\n` +
        `Please re-download the latest installer. If the problem persists contact support.`
      );
      app.quit();
      return;
    }
    cmd = pythonExe;
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
      'Server Start Failed',
      `Could not start the Python background server.\n\n` +
      `Error: ${err.message}\n` +
      `Python: ${cmd}\n` +
      `Working dir: ${projectDir}\n\n` +
      `This usually means the .venv was not bundled correctly. ` +
      `Please re-download the latest installer.`
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
  const preferredPorts = [8008, 8009, 8010];
  let started = false;
  let lastErr = null;

  for (const port of preferredPorts) {
    SERVER_PORT = port;
    startServer();
    try {
      // Give slower Windows machines enough time on first start.
      await waitForServer(150, 800);   // up to ~120 s
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
    const extra = startupExit && startupExit.logs
      ? `\n\nLast server logs:\n${startupExit.logs}`
      : '';
    const errMsg = lastErr ? `\nError: ${lastErr.message}\n` : '\n';
    dialog.showErrorBox(
      'Startup Failed',
      `The Python server could not start.\n${errMsg}` +
      `Data directory: ${USER_DATA_DIR}\n` +
      `Ports tried: 8002, 8003, 8004\n\n` +
      `Possible causes:\n` +
      `  • Antivirus blocking bundled Python\n` +
      `  • Incomplete installation (.venv or dependencies missing)\n` +
      `  • Corporate endpoint protection blocking localhost server\n` +
      extra
    );
    app.quit();
    return;
  }

  try {
    createWindow();
  } catch (err) {
    console.error('[Electron] Could not connect to server:', err.message);
    dialog.showErrorBox(
      'Startup Failed',
      `The Python server could not start within 32 seconds.\n\n` +
      `Data directory: ${USER_DATA_DIR}\n\n` +
      `Possible causes:\n` +
      `  • Antivirus blocking the bundled Python\n` +
      `  • Port ${SERVER_PORT} in use by another app\n` +
      `  • .venv missing from the installation\n\n` +
      `Please re-download the latest installer or contact support.`
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
