#!/usr/bin/env node
// Read Steam Cloud metadata through native Steam's authenticated CEF session.
// Steam must be started with -cef-enable-debugging; no cookies or tokens are
// extracted or persisted.

const appid = process.argv[2];
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

const socket = new WebSocket(target.webSocketDebuggerUrl);
let nextId = 0;
const pending = new Map();
socket.onmessage = (event) => {
  const message = JSON.parse(event.data);
  const callback = pending.get(message.id);
  if (callback) {
    pending.delete(message.id);
    callback(message.error ? new Error(JSON.stringify(message.error)) : null,
      message.result?.result?.value ?? message.result);
  }
};
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

await command("Page.navigate", {
  url: `https://store.steampowered.com/account/remotestorageapp/?appid=${appid}`,
});
for (let attempt = 0; attempt < 20; attempt += 1) {
  const ready = await command("Runtime.evaluate", {
    expression: "document.querySelectorAll('.accountTable tr').length > 1",
    returnByValue: true,
  });
  if (ready === true) break;
  await new Promise((resolve) => setTimeout(resolve, 500));
}
const files = await command("Runtime.evaluate", {
  expression: `(() => Array.from(document.querySelectorAll('.accountTable tr')).map((row) => {
    const cells = row.querySelectorAll('td');
    if (cells.length < 4) return null;
    const link = row.querySelector('a[href*="ugc"], a[href*="filedownload"], a[href*="steamusercontent"]');
    return { folder: cells[0].textContent.trim(), name: cells[1].textContent.trim(),
      size: cells[2].textContent.trim(), timestamp: cells[3].textContent.trim(),
      url: link ? link.href : '' };
  }).filter(Boolean))()`,
  returnByValue: true,
  awaitPromise: true,
});
process.stdout.write(`${JSON.stringify({ appid: Number(appid), files })}\n`);
socket.close();
