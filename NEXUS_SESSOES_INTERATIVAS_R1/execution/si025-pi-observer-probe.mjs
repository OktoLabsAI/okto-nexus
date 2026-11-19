import assert from "node:assert/strict";
import { syncBuiltinESMExports } from "node:module";
import { access, readFile, rename, writeFile } from "node:fs/promises";
import net from "node:net";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

let networkAttempts = 0;
function denyNetwork() {
  networkAttempts += 1;
  throw new Error("The Pi shared-owner probe has no network");
}
net.Socket.prototype.connect = denyNetwork;
globalThis.fetch = denyNetwork;
syncBuiltinESMExports();

const [release, cwd, agentDir, controlDir, sessionFlag, selectedSession] = process.argv.slice(2);
assert.ok(
  (sessionFlag === undefined && selectedSession === undefined) ||
  (sessionFlag === "--session-id" && /^hsess_[0-9a-f]{32}$/.test(selectedSession)),
);
const namespace = path.join(release, "node_modules", "@earendil-works");
const installed = path.join(namespace, "pi-coding-agent");
const pkg = JSON.parse(await readFile(path.join(installed, "package.json"), "utf8"));
assert.equal(pkg.version, "0.87.1");
assert.equal(process.version, "v24.15.0");
console.error("importing sdk");
const sdk = await import(pathToFileURL(path.join(installed, pkg.exports["."].import)).href);
console.error("importing provider");
const ai = await import(pathToFileURL(path.join(namespace, "pi-ai", "dist", "providers", "faux.js")).href);
const { InteractiveMode, ModelRuntime, SessionManager, SettingsManager } = sdk;

class CaptureTerminal {
  columns = 116;
  rows = 42;
  kittyProtocolActive = false;
  started = false;
  stopped = false;
  output = "";
  start(_acceptInput, _resize) { this.started = true; }
  stop() { this.stopped = true; }
  drainInput() { return Promise.resolve(); }
  write(chunk) {
    assert.ok(this.output.length + chunk.length < 1_000_000);
    this.output += chunk;
  }
  moveBy() {}
  hideCursor() {}
  showCursor() {}
  clearLine() {}
  clearFromCursor() {}
  clearScreen() {}
  setTitle() {}
  setProgress() {}
}

// Restrict process-wide lifecycle, extension binding and network setup to the
// RPC owner. These override points are internal to the examined Pi build.
class ObservingPi extends InteractiveMode {
  registerSignalHandlers() {}
  applyRuntimeSettings() {}
  async bindCurrentSessionExtensions() {}
}
const faux = ai.fauxProvider({ provider: "nexus-fixture", api: "nexus-fixture" });
console.error("loading model runtime");
const modelRuntime = await ModelRuntime.create({
  authPath: path.join(agentDir, "auth.json"), modelsPath: null,
  allowModelNetwork: false, refreshOnCreate: false,
});
console.error("registering provider");
modelRuntime.registerNativeProvider(faux.provider);
console.error("setting runtime fixture token");
await modelRuntime.setRuntimeApiKey(faux.provider.id, "synthetic-fixture-token");
let sessionCreations = 0;
console.error("creating agent session");
const owner = await sdk.createAgentSessionRuntime(async ({ cwd, agentDir, sessionManager }) => {
  sessionCreations += 1;
  const services = await sdk.createAgentSessionServices({
    cwd, agentDir, modelRuntime,
    settingsManager: SettingsManager.inMemory({ showTerminalProgress: false }),
    resourceLoaderOptions: {
      noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    },
  });
  const result = await sdk.createAgentSessionFromServices({
    services, sessionManager, model: faux.getModel(), noTools: "all",
  });
  return { ...result, services, diagnostics: services.diagnostics };
}, {
  cwd,
  agentDir,
  sessionManager: SessionManager.create(cwd, path.join(agentDir, "sessions"),
    selectedSession ? { id: selectedSession } : undefined),
});

const session = owner.session;
const sessionId = session.sessionId;
const presenterHost = {
  get session() { return owner.session; },
  setBeforeSessionInvalidate() {},
  setRebindSession() {},
};
const effects = [];
for (const method of ["prompt", "abort", "steer", "followUp", "bindExtensions"]) {
  const original = session[method].bind(session);
  session[method] = (...args) => {
    effects.push(method === "bindExtensions" ? `bind:${args[0].mode}` : method);
    return original(...args);
  };
}
let disposals = 0;
const dispose = owner.dispose.bind(owner);
owner.dispose = async () => {
  disposals += 1;
  await dispose();
  await record("owner-disposed", String(disposals));
};
let viewerAttaches = 0;
const probeText = "Owner prompt held by a deterministic local provider";
const resultText = "Native Pi rendered the answer from the same session";
const events = [];
async function attach() {
  const terminal = new CaptureTerminal();
  const viewer = new ObservingPi(presenterHost, { terminal, tuiMode: "transcript" });
  await viewer.init();
  assert.ok(terminal.started);
  assert.equal(owner.session, session);
  viewerAttaches += 1;
  return { viewer, terminal };
}
async function expectOutput(terminal, text) {
  for (let count = 0; count < 80 && !terminal.output.includes(text); count += 1) await delay(30);
  assert.ok(terminal.output.includes(text), text);
}
async function record(name, value) {
  const destination = path.join(controlDir, name);
  await writeFile(destination + ".tmp", value, "utf8");
  await rename(destination + ".tmp", destination);
}
async function checkpoint(name) {
  await record(name, sessionId);
  for (let count = 0; count < 500; count += 1) {
    try {
      await access(path.join(controlDir, `release-${name}`));
      return;
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    await delay(30);
  }
  throw new Error(`The runner did not release ${name}`);
}
let second;
faux.setResponses([async () => {
  assert.ok(session.isStreaming);
  const first = await attach();
  await expectOutput(first.terminal, probeText);
  await checkpoint("first-view");
  first.viewer.stop();
  assert.ok(first.terminal.stopped && session.isStreaming);
  await checkpoint("between-views");
  second = await attach();
  await expectOutput(second.terminal, probeText);
  await checkpoint("second-view");
  return ai.fauxAssistantMessage(resultText);
}]);
session.subscribe((event) => {
  events.push(event.type);
  if (event.type !== "agent_settled") return;
  void (async () => {
    await expectOutput(second.terminal, resultText);
    second.viewer.stop();
    assert.ok(second.terminal.stopped);
    assert.equal(owner.session, session);
    assert.equal(session.sessionId, sessionId);
    assert.equal(sessionCreations, 1);
    assert.equal(disposals, 0);
    assert.equal(networkAttempts, 0);
    assert.equal(faux.state.callCount, 1);
    assert.equal(viewerAttaches, 2);
    assert.deepEqual(effects, ["bind:rpc", "prompt"]);
    assert.equal(events.filter((type) => type === "agent_settled").length, 1);
    await record("summary.json", JSON.stringify({
      pi: pkg.version, node: process.version, sessionId,
      sessions_created: sessionCreations, renderer_attaches: viewerAttaches,
      owner_calls_before_rpc_eof: effects, disposals_before_rpc_eof: disposals,
      faux_model_calls: faux.state.callCount, network_attempts: networkAttempts, settled: 1,
    }));
  })().catch((error) => { console.error(error); process.exit(1); });
});
console.error("starting rpc");
await sdk.runRpcMode(owner);
