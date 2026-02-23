#!/usr/bin/env node
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const projectRoot = path.resolve(__dirname, "..");
const serverPath = path.join(projectRoot, "mcp_server.py");
const args = process.argv.slice(2);

if (!fs.existsSync(serverPath)) {
  console.error(`Error: mcp_server.py not found at ${serverPath}`);
  process.exit(1);
}

const child = spawn("python3", [serverPath, ...args], {
  stdio: "inherit",
  env: process.env,
});

child.on("error", (err) => {
  if (err && err.code === "ENOENT") {
    console.error("Error: python3 is not installed or not in PATH.");
  } else {
    console.error(`Error starting server: ${err.message}`);
  }
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
