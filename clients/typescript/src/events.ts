import type { Events } from "./generated/Events";

// a shape check only: the arguments' types are those the server's AsyncAPI document declares
function isEvent(value: unknown): value is Events {
  return (
    typeof value === "object" &&
    value !== null &&
    "presenter" in value &&
    typeof value.presenter === "string" &&
    "signal" in value &&
    typeof value.signal === "string" &&
    "args" in value &&
    Array.isArray(value.args)
  );
}

/** Open the event socket of the server at `base`; the returned function closes it. */
export function connect(base: string, on: (event: Events) => void): () => void {
  const socket = new WebSocket(`${base.replace(/^http/, "ws")}/api/events`);
  socket.onmessage = (message: MessageEvent<string>) => {
    const event: unknown = JSON.parse(message.data);
    if (isEvent(event)) {
      on(event);
    } else {
      console.warn("Ignored a message that is not an event:", event);
    }
  };
  return () => {
    socket.close();
  };
}
