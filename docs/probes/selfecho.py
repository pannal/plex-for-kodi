#!/usr/bin/env python3
"""Does the relay send your own State back to you?

twoclientprobe's observer applies remote state only when ignoringOnTheFly.server is falsy,
so it sat at pos=0 and kept echoing stale frames — and those echoed frames came BACK to it,
labelled setBy=<its own identity>. The doc currently claims the opposite ("0 inbound doSeek
frames -> sender gets no echo of its own seek", §7). Worth isolating, because if true the
self-ignore is mandatory, not optional.

Three single-client questions, each in its own throwaway room so nothing interferes:

  E1  a lone client: do you ever see a frame whose setBy is YOUR identity?
  E2  is the echo's playstate your own, or the relay's extrapolation of it?
  E3  do you see your own doSeek? (the doc's specific claim) and doSeek:true frames in
      general, which is what makes a seek look like it propagated when it did not.

Usage: python3 selfecho.py
"""
import json
import sys
import threading
import time
import uuid

sys.argv = [sys.argv[0]]
import twoclientprobe as tc                        # noqa: E402


def trial(label, driver, seconds=9.0):
    tc.ROOM = "wt" + uuid.uuid4().hex[:8]
    c = tc.Client("SELF", 4242, "self-" + uuid.uuid4().hex[:6], driver=driver)
    c.start()
    time.sleep(0.8)
    c.announce()
    time.sleep(1.5)
    c.set_local(position=333.0, paused=False)
    if driver:
        c.set_local(do_seek=True)
    time.sleep(seconds)
    c.set_local(do_seek=False)
    time.sleep(2.0)
    rows = tc.snap(c, c.msgs[0][0])
    c.close()
    return rows


def analyse(label, rows):
    print("\n" + "=" * 74)
    print("== " + label)
    print("=" * 74)
    if not rows:
        print("   no State observed")
        return
    for i, (paused, pos, do_seek, setby) in enumerate(rows):
        tag = "  <-- MY OWN IDENTITY" if setby == "SELF" else ""
        print("   #%-2d paused=%-5s pos=%-10s doSeek=%-5s setBy=%s%s"
              % (i, paused, round(pos, 3) if isinstance(pos, float) else pos,
                 do_seek, setby, tag))
    mine = [r for r in rows if r[3] == "SELF"]
    seeks = [r for r in rows if r[2]]
    print("   frames total %d | with MY setBy %d | with doSeek %d"
          % (len(rows), len(mine), len(seeks)))
    print("   VERDICT: %s"
          % ("YES -- you receive your own State back, so self-ignore is MANDATORY"
             if mine else "no -- the relay suppresses your own frames, as the doc says"))


def main():
    tc.rule("E1/E2  lone client that is the driver, after announcing a seek")
    analyse("driver, seeks to 333", trial("driver", driver=True))

    tc.rule("E3  lone client that is the observer (applies remote state)")
    analyse("observer", trial("observer", driver=False))

    tc.rule("SUMMARY")
    print("   If 'MY setBy' frames appear, §7's '0 inbound doSeek frames -> sender gets no")
    print("   echo of its own seek' needs correcting: the sender DOES get its frames back,")
    print("   and a conforming client must drop any frame whose setBy is its own identity.")


if __name__ == "__main__":
    main()
