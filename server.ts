import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PYTHON_PORT = Number(process.env.DBMONITOR_API_PORT ?? '8000');
const PYTHON_HOST = process.env.DBMONITOR_API_HOST ?? '127.0.0.1';
const PORT = Number(process.env.PORT ?? '3000');
const IS_PROD = process.env.NODE_ENV === 'production';

let pythonProc: ChildProcess | null = null;

function startPythonPlatform(): ChildProcess {
  const scriptPath = path.resolve(__dirname, 'dbmonitor', 'run_platform.py');
  const child = spawn('python3', [scriptPath], {
    cwd: __dirname,
    env: {
      ...process.env,
      DBMONITOR_API_HOST: PYTHON_HOST,
      DBMONITOR_API_PORT: String(PYTHON_PORT),
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  child.stdout?.on('data', (chunk: Buffer) => {
    process.stdout.write(`[python] ${chunk.toString()}`);
  });
  child.stderr?.on('data', (chunk: Buffer) => {
    process.stderr.write(`[python] ${chunk.toString()}`);
  });
  child.on('exit', (code, signal) => {
    console.error(`Python platform exited (code=${code}, signal=${signal})`);
  });
  return child;
}

async function waitForPythonHealth(timeoutMs = 15000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const ok = await new Promise<boolean>((resolve) => {
      const req = http.get(
        {
          hostname: PYTHON_HOST,
          port: PYTHON_PORT,
          path: '/health',
          timeout: 1000,
        },
        (res) => {
          res.resume();
          resolve(res.statusCode === 200);
        }
      );
      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
    });
    if (ok) {
      return;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error('Timed out waiting for Python DBMonitor platform API on port ' + PYTHON_PORT);
}

function proxyToPython(req: express.Request, res: express.Response): void {
  const proxyReq = http.request(
    {
      hostname: PYTHON_HOST,
      port: PYTHON_PORT,
      path: req.originalUrl,
      method: req.method,
      headers: {
        ...req.headers,
        host: `${PYTHON_HOST}:${PYTHON_PORT}`,
      },
    },
    (proxyRes) => {
      res.status(proxyRes.statusCode ?? 502);
      for (const [key, val] of Object.entries(proxyRes.headers)) {
        if (val !== undefined) {
          res.setHeader(key, val);
        }
      }
      proxyRes.pipe(res);
    }
  );

  proxyReq.on('error', (err) => {
    if (!res.headersSent) {
      res.status(502).json({ error: `Python backend unreachable: ${err.message}` });
    }
  });

  req.pipe(proxyReq);
}

async function bootstrap(): Promise<void> {
  pythonProc = startPythonPlatform();
  await waitForPythonHealth();

  const app = express();
  app.use('/api', (req, res) => {
    proxyToPython(req, res);
  });

  if (!IS_PROD) {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.resolve(__dirname, 'dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      const indexHtml = path.join(distDir, 'index.html');
      if (fs.existsSync(indexHtml)) {
        res.sendFile(indexHtml);
      } else {
        res.status(404).send('Build output not found.');
      }
    });
  }

  const server = app.listen(PORT, '0.0.0.0', () => {
    console.log(`DBMonitor web server listening on http://0.0.0.0:${PORT} -> Python API :${PYTHON_PORT}`);
  });

  const shutdown = () => {
    server.close();
    if (pythonProc && !pythonProc.killed) {
      pythonProc.kill('SIGTERM');
    }
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

bootstrap().catch((err) => {
  console.error(err);
  if (pythonProc && !pythonProc.killed) {
    pythonProc.kill('SIGTERM');
  }
  process.exit(1);
});
