export type RedsunEvent =
  | { presenter: "positioner"; signal: "sig_readback"; args: [string, string, number] }
  | { presenter: "positioner"; signal: "sig_moving"; args: [string, boolean] }
  | { presenter: "positioner"; signal: "sig_limits"; args: [string, string, unknown, unknown] }
  | { presenter: "positioner"; signal: "sig_failed"; args: [string, string] }
  | { presenter: "positioner"; signal: "sig_configuration"; args: [string, unknown] }
  | { presenter: "lights"; signal: "sig_enabled"; args: [string, boolean] }
  | { presenter: "lights"; signal: "sig_intensity"; args: [string, number] }
  | { presenter: "lights"; signal: "sig_failed"; args: [string, string] }
  | { presenter: "lights"; signal: "sig_configuration"; args: [string, unknown] };

/** Open the event socket of the server at `base`; the returned function closes it. */
export function connect(base: string, on: (event: RedsunEvent) => void): () => void {
  const socket = new WebSocket(`${base.replace(/^http/, "ws")}/api/events`);
  socket.onmessage = (message) => on(JSON.parse(message.data) as RedsunEvent);
  return () => socket.close();
}
