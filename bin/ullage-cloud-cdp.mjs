#!/usr/bin/env node
// Read Steam Cloud metadata and file bytes through native Steam's authenticated CEF session.
// Steam must be started with -cef-enable-debugging; no cookies or tokens are
// extracted or persisted.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const appid = process.argv[2];
const includeData = process.argv.includes("--include-data");
if (!/^[0-9]+$/.test(appid || "")) {
  console.error("usage: ullage-cloud-cdp.mjs APPID");
  process.exit(2);
}

const response = await fetch("http://127.0.0.1:8080/json");
if (!response.ok) throw new Error(`Steam CDP unavailable: HTTP ${response.status}`);
const targets = await response.json();
const target = targets.find((item) => item.type === "page" && item.webSocketDebuggerUrl &&
  item.url?.includes("store.steampowered.com")) ||
  targets.find((item) => item.type === "page" && item.webSocketDebuggerUrl &&
    item.url?.includes("steamloopback.host"));
if (!target) throw new Error("Steam CDP has no page target");

let socket = new WebSocket(target.webSocketDebuggerUrl);
let nextId = 0;
const pending = new Map();
function handleMessage(event) {
  const message = JSON.parse(event.data);
  const callback = pending.get(message.id);
  if (callback) {
    pending.delete(message.id);
    callback(message.error ? new Error(JSON.stringify(message.error)) : null,
      message.result?.result?.value ?? message.result);
  }
}
socket.onmessage = handleMessage;
await new Promise((resolve, reject) => {
  socket.onopen = resolve;
  socket.onerror = () => reject(new Error("Steam CDP WebSocket connection failed"));
});

function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, (error, value) => error ? reject(error) : resolve(value));
    socket.send(JSON.stringify({ id, method, params }));
  });
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function downloadName(item) {
  return `%${item.folder}%${item.name}`.replace(/[\\/]/g, "_");
}

async function waitForDownload(directory, before, expectedName) {
  const deadline = Date.now() + 60000;
  let previousPath = "";
  let previousSize = -1;
  let stableReads = 0;
  while (Date.now() < deadline) {
    const newCandidates = fs.readdirSync(directory)
      .filter((name) => !before.has(name) && !name.endsWith(".crdownload"));
    const candidates = fs.existsSync(path.join(directory, expectedName))
      ? [expectedName]
      : newCandidates.length === 1 ? newCandidates : [];
    if (candidates.length === 1) {
      const candidate = path.join(directory, candidates[0]);
      const stat = fs.statSync(candidate);
      if (stat.isFile()) {
        if (candidate === previousPath && stat.size === previousSize) {
          stableReads += 1;
        } else {
          previousPath = candidate;
          previousSize = stat.size;
          stableReads = 0;
        }
        if (stableReads >= 2) return candidate;
      }
    }
    await sleep(100);
  }
  throw new Error(`Steam Cloud download did not finish within 60 seconds: ${expectedName}`);
}

const cloudUrl = `https://store.steampowered.com/account/remotestorageapp/?appid=${appid}`;
const fileRowsExpression = `(() => Array.from(document.querySelectorAll('.accountTable tr')).map((row) => {
  const cells = row.querySelectorAll('td');
  if (cells.length < 4) return null;
  const link = row.querySelector('a[href*="ugc"], a[href*="filedownload"], a[href*="steamusercontent"]');
  return { folder: cells[0].textContent.trim(), name: cells[1].textContent.trim(),
    size: cells[2].textContent.trim(), timestamp: cells[3].textContent.trim(),
    url: link ? link.href : '' };
}).filter(Boolean))()`;

async function waitForCloudTable() {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const ready = await command("Runtime.evaluate", {
      expression: "document.querySelectorAll('.accountTable tr').length > 1",
      returnByValue: true,
    });
    if (ready === true) return;
    await sleep(500);
  }
  throw new Error("Steam Cloud page did not expose its file table");
}

const created = await command("Target.createTarget", {
  url: cloudUrl,
});
socket.close();
let childTarget;
for (let attempt = 0; attempt < 20 && !childTarget; attempt += 1) {
  const pages = await (await fetch("http://127.0.0.1:8080/json")).json();
  childTarget = pages.find((item) => item.id === created.targetId);
  if (!childTarget) await new Promise((resolve) => setTimeout(resolve, 250));
}
if (!childTarget?.webSocketDebuggerUrl) throw new Error("Steam CDP child page did not appear");
socket = new WebSocket(childTarget.webSocketDebuggerUrl);
socket.onmessage = handleMessage;
pending.clear();
await new Promise((resolve, reject) => {
  socket.onopen = resolve;
  socket.onerror = () => reject(new Error("Steam CDP child connection failed"));
});
await command("Page.enable");
await waitForCloudTable();
const files = await command("Runtime.evaluate", {
  expression: fileRowsExpression,
  returnByValue: true,
  awaitPromise: true,
});
const downloadDirectory = includeData
  ? fs.mkdtempSync(path.join(os.tmpdir(), "ullage-cloud-"))
  : null;
try {
  if (includeData && files.length) {
    await command("Page.setDownloadBehavior", {
      behavior: "allow",
      downloadPath: downloadDirectory,
    });
    for (const item of files) {
      // filedownload links are short-lived; refresh the row immediately before
      // navigation so a large Cloud set does not leave the last entries stale.
      await command("Page.navigate", { url: cloudUrl });
      await waitForCloudTable();
      const folder = JSON.stringify(item.folder);
      const name = JSON.stringify(item.name);
      item.url = await command("Runtime.evaluate", {
        expression: `(() => { for (const row of document.querySelectorAll('.accountTable tr')) {
          const cells = row.querySelectorAll('td');
          if (cells.length >= 4 && cells[0].textContent.trim() === ${folder} &&
              cells[1].textContent.trim() === ${name})
            return row.querySelector('a[href*="ugc"], a[href*="filedownload"], a[href*="steamusercontent"]')?.href || '';
        } return ''; })()`,
        returnByValue: true,
      });
      if (!item.url) throw new Error(`Steam Cloud file has no download URL: ${item.name}`);
      const before = new Set(fs.readdirSync(downloadDirectory));
      await command("Page.navigate", { url: item.url });
      const downloaded = await waitForDownload(downloadDirectory, before, downloadName(item));
      item.data = fs.readFileSync(downloaded).toString("base64");
    }
  }
} finally {
  // The child page is temporary. Close it so authenticated Cloud reads do not
  // leave a Steam browser window covering the game launched underneath it.
  await command("Page.close").catch(() => {});
  socket.close();
  if (downloadDirectory) fs.rmSync(downloadDirectory, { recursive: true, force: true });
}
process.stdout.write(`${JSON.stringify({ appid: Number(appid), files })}\n`);
