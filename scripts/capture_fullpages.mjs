import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const outDir = "/opt/cursor/artifacts";
const port = 8765;
const shots = [
  ["profile", "index.html", 390, true],
  ["profile-hero-390x900", "index.html", 390, false, 900],
  ["plan", "development.html", 390, true],
  ["profile-1280", "index.html", 1280, true],
];

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

let server = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1"], {
  cwd: root,
  stdio: "ignore",
});
await sleep(500);

try {
  await mkdir(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  for (const [name, file, width, full, height] of shots) {
    const page = await browser.newPage({ viewport: { width, height: height || 800 } });
    await page.goto(`http://127.0.0.1:${port}/${file}`, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForTimeout(400);
    const out = path.join(outDir, `redesign-v11-${name}.png`);
    await page.screenshot({ path: out, fullPage: Boolean(full) });
    await page.close();
    console.log("wrote", out);
  }
  await browser.close();
} finally {
  server.kill("SIGTERM");
}