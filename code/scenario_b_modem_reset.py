#!/usr/bin/env python3
"""
scenario_b_modem_reset.py — "The modem is the problem."

Hypothesis: with the antenna attached and the modem registered, the RF
re-registration inrush during a modem reconnect sags the +3V rail — even
without heavy CPU/I/O load — showing the trigger is modem/RF consumption,
not compute load.

Setup:
  - Antenna ATTACHED, modem registered on a live network.
  - Repeated modem full resets (AT+CFUN=1,1 = disconnect + reconnect).
  - NO heavy CPU/I/O load (or minimal), to isolate the modem's contribution.
  - +3V rail minimum sampled across each reconnect.

Result of interest: per-cycle dip depth and any crash, versus Scenario A.

Env: DUT_SSH, DWF_LIB   (see rail_monitor_lib.py)
Usage:
  python3 scenario_b_modem_reset.py [--cycles 30]
"""
import argparse, time, datetime
import rail_monitor_lib as rl

THRESH = 3.20
BROWNOUT = 2.90

ap = argparse.ArgumentParser()
ap.add_argument("--cycles", type=int, default=30)
ap.add_argument("--log", default="scenario_b.log")
args = ap.parse_args()

log = open(args.log, "a")
def emit(s):
    print(s, flush=True); log.write(s + "\n"); log.flush()
def now(): return datetime.datetime.now().isoformat(timespec="milliseconds")

emit("=" * 60)
emit(f" SCENARIO B — MODEM RESET, ANTENNA ON (no heavy load)  {now()}")
emit(f" cycles={args.cycles}")
emit("=" * 60)

if not rl.alive():
    emit("device not reachable"); raise SystemExit(1)

port = rl.find_at_port()
if not port:
    emit("modem AT port not found — is the modem powered/enumerated?")
    raise SystemExit(1)
sig = rl.modem_signal(port)
emit(f" modem at {port}; signal: {sig}")
emit(" (Scenario B expects the antenna ATTACHED and modem registered.)")

scope = rl.RailScope()
emit(f" idle baseline +3V_min={scope.min_over(2):.3f}V  UV={rl.hw_undervoltage()}")

dips = 0; crashes = 0; worst = 99.0
i = 1
while i <= args.cycles:
    port = rl.find_at_port()          # re-detect (port can move across resets)
    if not port:
        emit(f" cycle {i}: AT port not found, retrying"); time.sleep(3); continue
    rl.modem_reset(port)              # disconnect + reconnect -> RF inrush
    mn = scope.min_over(6)            # capture the reconnect window
    if mn < worst:
        worst = mn
    up = rl.alive()
    dip = mn < THRESH
    if dip:
        dips += 1
    flag = ("  DIP" if dip else "") + ("  DEEP" if mn < BROWNOUT else "") + \
           ("  *** CRASH ***" if not up else "")
    emit(f" cycle {i:2d}/{args.cycles}  +3V_min={mn:.3f}V  "
         f"{'UP' if up else 'DOWN'}  UV={rl.hw_undervoltage() if up else '?'}{flag}")
    if not up:
        crashes += 1
        emit("  waiting for recovery (up to 180s)...")
        rec = False
        for _ in range(36):
            time.sleep(5)
            if rl.alive():
                rec = True; emit(f"  recovered {now()}"); break
        if not rec:
            emit("  *** did not recover — cold power-cycle the board, then it "
                 "will resume ***")
            while not rl.alive():
                time.sleep(15)
            emit(f"  board back {now()}")
    i += 1
    time.sleep(1)

rate = 100.0 * crashes / args.cycles
emit("-" * 60)
emit(f" RESULT: dips={dips}/{args.cycles}  crashes={crashes}/{args.cycles} "
     f"({rate:.0f}%)  worst_+3V={worst:.3f}V")
if dips > 0 or crashes > 0:
    emit(" => Modem reconnect (antenna on) sags the rail with NO heavy load.")
    emit("    The trigger is modem/RF consumption, not compute load.")
else:
    emit(" => No dips this run; try more cycles or verify antenna/registration.")
emit("=" * 60)
scope.close(); log.close()
