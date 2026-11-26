import type { paths } from "./api";
import { connect } from "./events";

type PostPath = {
  [P in keyof paths]: paths[P] extends { post: { requestBody: unknown } } ? P : never;
}[keyof paths];
type Body<P extends PostPath> = paths[P] extends {
  post: { requestBody: { content: { "application/json": infer B } } };
}
  ? B
  : never;
type GetPath = {
  [P in keyof paths]: paths[P] extends { get: unknown } ? P : never;
}[keyof paths];
type Reply<P extends GetPath> = paths[P] extends {
  get: { responses: { 200: { content: { "application/json": infer R } } } };
}
  ? R
  : never;

const base = new URLSearchParams(location.search).get("base") ?? "http://127.0.0.1:8000";
const STEP = 1;

function byId(id: string): HTMLElement {
  const found = document.getElementById(id);
  if (!found) throw new Error(`index.html has no element with id "${id}"`);
  return found;
}

function show(error: unknown): void {
  byId("error").textContent = String(error);
}

async function call(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${base}${path}`, init);
  if (!response.ok) throw new Error(`${path}: ${String(response.status)} ${await response.text()}`);
  return response.json();
}

async function get<P extends GetPath>(path: P): Promise<Reply<P>> {
  return (await call(path)) as Reply<P>;
}

async function post<P extends PostPath>(path: P, body: Body<P>): Promise<void> {
  await call(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> = {},
  ...children: Node[]
): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

async function drawAxes(container: HTMLElement): Promise<void> {
  const stage = await get("/api/positioner/axes");
  for (const [device, axes] of Object.entries(stage)) {
    for (const [axis, info] of Object.entries(axes)) {
      const readback = element("span", {
        id: `readback-${device}-${axis}`,
        textContent: `${String(info.readback.value)} ${info.readback.units ?? ""}`,
      });
      const move = (delta: number) => () =>
        post("/api/positioner/move", { device, axis, delta }).catch(show);
      container.append(
        element(
          "div",
          { className: "row" },
          element("span", { className: "name", textContent: `${device} ${axis}` }),
          element("button", { textContent: String(-STEP), onclick: move(-STEP) }),
          readback,
          element("button", { textContent: `+${String(STEP)}`, onclick: move(STEP) }),
        ),
      );
    }
  }
}

async function drawLights(container: HTMLElement): Promise<void> {
  const lights = await get("/api/lights/lights");
  for (const [device, info] of Object.entries(lights)) {
    const enabled = element("input", {
      type: "checkbox",
      id: `enabled-${device}`,
      checked: info.enabled,
      onchange: () =>
        post("/api/lights/set_enabled", { device, on: enabled.checked }).catch(show),
    });
    const intensity = element("input", {
      type: "number",
      id: `intensity-${device}`,
      value: String(info.intensity?.value ?? 0),
      onchange: () =>
        post("/api/lights/set_intensity", { device, value: Number(intensity.value) }).catch(show),
    });
    container.append(
      element(
        "div",
        { className: "row" },
        element("span", { className: "name", textContent: device }),
        enabled,
        intensity,
      ),
    );
  }
}

async function main(): Promise<void> {
  await Promise.all([
    drawAxes(byId("axes")),
    drawLights(byId("lights")),
  ]);
  connect(base, (event) => {
    switch (event.signal) {
      case "sig_readback": {
        const [device, axis, value] = event.args;
        const label = document.getElementById(`readback-${device}-${axis}`);
        if (label) label.textContent = String(value);
        break;
      }
      case "sig_enabled": {
        const [device, on] = event.args;
        const box = document.getElementById(`enabled-${device}`) as HTMLInputElement | null;
        if (box) box.checked = on;
        break;
      }
      case "sig_intensity": {
        const [device, value] = event.args;
        const field = document.getElementById(`intensity-${device}`) as HTMLInputElement | null;
        if (field) field.value = String(value);
        break;
      }
      case "sig_failed":
        show(`${event.presenter}: ${event.args.join(": ")}`);
        break;
    }
  });
}

main().catch(show);
