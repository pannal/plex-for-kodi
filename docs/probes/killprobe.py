#!/usr/bin/env python3
"""§11.13 — when does the relay tell PEERS that a client is gone?

The old reading was "a hard-killed client produced no `left` and stayed in the roster."
That could not have been observed correctly by the dying client itself: once your socket
is gone you cannot hear your own departure. So this observes from a *third* client that
keeps echoing and therefore survives the whole window.

Three ways for the victim to stop, all at t=6 s in a fresh room:

    stop_sending   socket stays open, client just goes quiet
    socket_close   abrupt TCP close, NO WebSocket Close frame
    ws_close       proper WebSocket Close frame

Expected outcomes under two separate mechanisms:

    transport death  -> peers see `left` in ~0.2 s, Close frame or not
    live but silent  -> nothing until the 13.21 s silence timer (§5.8, §11.17)

Three clients per trial, one throwaway `kl<hex>` room each. Never touches a real room.
stdlib only.

Usage: python3 killprobe.py [host] [port]
"""
import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0]]
import twoclientprobe as tcp
import evictprobe as ev

class Echoer(tcp.Client):
    HALT=None
    def keepalive(self):
        while not self.stop.is_set():
            if getattr(self,'HALT',None) is not None and self.HALT.is_set():
                self.stop.wait(0.5); continue
            self.echo(); self.stop.wait(1.0)

def seen(obs, who):
    for _,m in obs.msgs:
        u=m.get('Set',{}).get('user') if isinstance(m.get('Set'),dict) else None
        if not isinstance(u,dict): continue
        for k,v in u.items():
            if isinstance(v,dict) and k.startswith(who) and v.get('event',{}).get('left'):
                return True
    return False

def scenario(kind, act_at=6.0, limit=40.0):
    tcp.ROOM='o2'+os.urandom(3).hex()
    ev.Driver.RATE=1.0
    d=ev.Driver("driver","111111111","drv",True); time.sleep(0.5)
    v=Echoer("victim","222222222","vic",False); v.HALT=threading.Event()
    time.sleep(0.4)
    o=Echoer("observer","333333333","obs",False)   # echoing -> never evicted
    t0=time.monotonic(); d.start(); v.start(); o.start()
    acted=False; got=None
    while time.monotonic()-t0<limit:
        el=time.monotonic()-t0
        if not acted and el>=act_at:
            if kind=='stop_sending': v.HALT.set()
            elif kind=='socket_close':
                v.HALT.set(); v.stop.set()
                try: v.sock.close()
                except OSError: pass
            elif kind=='ws_close': v.HALT.set(); v.close()
            acted=True
        if acted and seen(o, v.identity): got=el; break
        time.sleep(0.05)
    # is the victim still in the observer's roster at the end?
    import json as _j
    last=[m for _,m in o.msgs if 'List' in m]
    inroster=None
    if last:
        room=last[-1].get('List',{}).get(tcp.ROOM,{})
        inroster=[k for k in room if k.startswith(v.identity)]
    for c in (v,o,d):
        if not c.stop.is_set(): c.close()
    time.sleep(0.4)
    print("  %-14s peer saw `left`=%-9s   victim still in roster at end: %s"%(
        kind, ("%.2fs"%got) if got else "NONE", inroster if inroster else "no"))

def main():
    print("=== §11.13 transport death vs silence ===")
    print("full window, observer echoing so it survives:")
    for k in ("stop_sending", "socket_close", "ws_close"):
        scenario(k)


if __name__ == "__main__":
    main()
