import type { components } from "./api";

export type RedsunEvent = components["schemas"]["RedsunEvent"];

/** Open the event socket of the server at `base`; the returned function closes it. */
export function connect(base: string, on: (event: RedsunEvent) => void): () => void {
  const socket = new WebSocket(`${base.replace(/^http/, "ws")}/api/events`);
  socket.onmessage = (message) => on(JSON.parse(message.data) as RedsunEvent);
  return () => socket.close();
}
