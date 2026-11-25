import type { Events } from "./generated/Events";

/** Open the event socket of the server at `base`; the returned function closes it. */
export function connect(base: string, on: (event: Events) => void): () => void {
  const socket = new WebSocket(`${base.replace(/^http/, "ws")}/api/events`);
  socket.onmessage = (message) => on(JSON.parse(message.data) as Events);
  return () => socket.close();
}
