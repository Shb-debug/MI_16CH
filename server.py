from __future__ import annotations
import argparse, asyncio, json, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import websockets
from config import load_config

ROOT = Path(__file__).resolve().parent
class Hub:
    def __init__(self, demo: bool):
        self.demo, self.loop, self.running = demo, None, True
        self.clients: set[Any] = set()
        self.arm_client = None
        self.last = {"type":"status","mode":"demo" if demo else "real","lsl_connected":False,"model_ready":False,"simulated":demo,"state":"DEMO" if demo else "BLOCKED","message":"演示模式" if demo else "等待 LSL EEG"}
    async def ws(self, websocket, path=None):
        self.clients.add(websocket)
        await websocket.send(json.dumps(self.last, ensure_ascii=False))
        try:
            async for raw in websocket:
                try:
                    command = json.loads(raw).get("action")
                except (TypeError, json.JSONDecodeError):
                    command = None
                if command in {"start", "drop", "end"}:
                    await self.broadcast({"type": "ui_control", "action": command})
                    if command == "drop" and self.arm_client and not self.demo:
                        threading.Thread(target=self._send_home, daemon=True).start()
        finally: self.clients.discard(websocket)
    async def broadcast(self, item):
        if self.clients:
            await asyncio.gather(*(c.send(json.dumps(item, ensure_ascii=False)) for c in tuple(self.clients)), return_exceptions=True)
    def publish(self, item):
        if item.get("type") == "status":
            self.last = {**self.last, **item}
            print("[STATUS] %s" % json.dumps(item, ensure_ascii=False), flush=True)
        if item.get("type") == "mi_telemetry":
            print("[MI] probability=%.4f state=%s quality=%s" % (float(item.get("mi_probability", 0.0)), item.get("state", "UNKNOWN"), "OK" if item.get("quality_valid") else "BLOCKED"), flush=True)
        if self.loop and self.loop.is_running(): asyncio.run_coroutine_threadsafe(self.broadcast(item), self.loop)
        if item.get("type") == "mi_event" and item.get("mode") == "real" and not item.get("simulated") and self.arm_client:
            threading.Thread(target=self._send_arm_event, args=(item,), daemon=True).start()

    def _send_arm_event(self, item):
        try:
            result = self.arm_client.request({
                "command": item.get("command"),
                "event_id": str(item.get("event_id")),
                "confidence": item.get("confidence"),
            })
            self.publish({"type": "arm_status", **result, "event_id": str(item.get("event_id"))})
        except Exception as exc:
            self.publish({"type": "arm_status", "state": "ERROR", "reason": str(exc), "event_id": str(item.get("event_id"))})

    def _send_home(self):
        try:
            result = self.arm_client.request({"command": "MOVE_POSE", "pose": "home"})
            self.publish({"type": "arm_status", **result, "pose": "home"})
        except Exception as exc:
            self.publish({"type": "arm_status", "state": "ERROR", "pose": "home", "reason": str(exc)})
    async def demo_loop(self):
        n = 0
        while self.running:
            p = .12
            if n % 24 in (10, 11, 12): p = (.35, .62, .83)[n % 24 - 10]
            self.publish({"type":"mi_telemetry","mode":"demo","simulated":True,"model_ready":True,"state":"CANDIDATE" if p>.3 else "REST","mi_probability":p,"quality_valid":True,"sample_rate":125,"timestamp":time.time()})
            if n % 24 == 13: self.publish({"type":"mi_event","event_id":"demo-%d"%n,"command":"LEFT_HAND_GRASP","confidence":.89,"mode":"demo","simulated":True,"timestamp":time.time()})
            n += 1; await asyncio.sleep(.3)
    async def run(self, config):
        self.loop = asyncio.get_running_loop()
        if config.get("arm_bridge_enabled") and not self.demo:
            from arm_client import ArmBridgeClient
            self.arm_client = ArmBridgeClient(config.get("arm_bridge_host", "127.0.0.1"), int(config.get("arm_bridge_port", 8766)), float(config.get("arm_bridge_timeout_seconds", 1.0)))
        if self.demo: asyncio.create_task(self.demo_loop())
        else:
            from acquisition_lsl import LSLAcquisition
            threading.Thread(target=LSLAcquisition(config, self.publish).run, daemon=True).start()
        async with websockets.serve(self.ws, config["websocket_host"], int(config["websocket_port"])):
            print("[PAGE] http://%s:%d/index.html%s" % (config["websocket_host"], config["http_port"], "?demo=1" if self.demo else ""))
            while self.running: await asyncio.sleep(.5)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/"frontend"),**kwargs)
    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            body=json.dumps({"ok":True,"service":"mi-server"}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body); return
        super().do_GET()
    def log_message(self,*args): pass

def main():
    p=argparse.ArgumentParser(); p.add_argument("--config",default="mi_config.json"); p.add_argument("--demo",action="store_true"); a=p.parse_args()
    c=load_config(a.config); http=ThreadingHTTPServer((c["websocket_host"],int(c["http_port"])),Handler); threading.Thread(target=http.serve_forever,daemon=True).start()
    hub=Hub(a.demo)
    try: asyncio.run(hub.run(c))
    except KeyboardInterrupt: hub.running=False
    finally: http.shutdown(); http.server_close()
if __name__=="__main__": main()
