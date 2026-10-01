import { decode, encode } from "@msgpack/msgpack";
import { StreamCommand } from "@rideprep/course-format";
import { WebSocketServer, WebSocket } from "ws";
import { RideEngine } from "./engine";

/** Local WebSocket state server: MessagePack StreamState at 50 Hz, commands back over the same socket. */
export function serve(engine: RideEngine, opts: { host?: string; port?: number; packageUrl: string; onCommand?: (c: StreamCommand) => void }) {
  const wss = new WebSocketServer({ host: opts.host ?? "127.0.0.1", port: opts.port ?? 8765, perMessageDeflate: false });
  wss.on("connection", (ws: WebSocket) => {
    ws.send(encode(engine.hello(opts.packageUrl)));
    const off = engine.onState((buf) => {
      if (ws.readyState === WebSocket.OPEN && ws.bufferedAmount < 1 << 20) ws.send(buf);
    });
    ws.on("message", (data) => {
      try {
        const c = decode(data as Uint8Array) as StreamCommand;
        engine.command(c);
        opts.onCommand?.(c);
      } catch (e) {
        console.warn("bad command", e);
      }
    });
    ws.on("close", () => off());
  });
  return wss;
}
