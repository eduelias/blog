#!/usr/bin/env python3
"""
scenario_a_load_only.py — "Load is not the problem."

Hypothesis: sustained high CPU + I/O load, on its own, does NOT sag the +3V
rail into the brown-out zone or crash the device.

Setup:
  - Antenna DETACHED (or modem idle) — no RF activity.
  - NO modem reset during the run.
  - Heavy CPU + memory load, plus optional disk I/O load, held for the duration.
  - The +3V rail minimum is sampled the whole time on the AD3.

Pass criterion: rail stays well above the brown-out threshold and the device
never crashes, demonstrating that load alone is not the trigger.

Env: DUT_SSH, DWF_LIB   (see rail_monitor_lib.py)
Usage:
  python3 scenario_a_load_only.py [--minutes 5] [--io]
"""
import argparse, time, datetime
import rail_monitor_lib as rl

THRESH = 3.20
BROWNOUT = 2.90

ap = argparse.ArgumentParser()
ap.add_argument("--minutes", type=float, default=5.0)
ap.add_argument("--io", action="store_true", help="also run disk I/O load")
ap.add_argument("--log", default="scenario_a.log")
args = ap.parse_args()

log = open(args.log, "a")
def emit(s):
    print(s, flush=True); log.write(s + "\n"); log.flush()
def now(): return datetime.datetime.now().isoformat(timespec="milliseconds")

emit("=" * 60)
emit(f" SCENARIO A — LOAD ONLY (no modem reset)  {now()}")
emit(f" duration={args.minutes} min  io={args.io}")
emit("=" * 60)

if not rl.alive():
    emit("device not reachable"); raise SystemExit(1)

# Confirm the modem is idle / antenna context (informational only)
port = rl.find_at_port()
if port:
    emit(f" modem present at {port}; signal: {rl.modem_signal(port)}")
    emit(" (Scenario A expects the antenna detached / no reconnects.)")

scope = rl.RailScope()
rl.push_load_helper()

emit(f" idle baseline +3V_min={scope.min_over(2):.3f}V  UV={rl.hw_undervoltage()}")

loadp = rl.start_cpu_load()
iop = rl.start_io_load() if args.io else None
time.sleep(3)
emit(" heavy load running (CPU+mem" + (" +IO" if args.io else "") + ")")

t_end = time.time() + args.minutes * 60
worst = 99.0; crashed = False; sec = 0
while time.time() < t_end:
    mn = scope.min_over(5)
    if mn < worst:
        worst = mn
    up = rl.alive()
    sec += 5
    flag = ("  DIP" if mn < THRESH else "") + ("  DEEP" if mn < BROWNOUT else "")
    emit(f"  t+{sec:4d}s  +3V_min={mn:.3f}V  {'UP' if up else '*** DOWN ***'}"
         f"  UV={rl.hw_undervoltage()}{flag}")
    if not up:
        crashed = True
        emit("  device unreachable under load-only — unexpected!")
        break

rl.stop_cpu_load()
if iop:
    rl.stop_io_load()
    try: iop.wait(timeout=5)
    except: iop.kill()
try: loadp.wait(timeout=5)
except: loadp.kill()

emit("-" * 60)
emit(f" RESULT: worst_+3V={worst:.3f}V  crashed={crashed}")
if not crashed and worst >= BROWNOUT:
    emit(" => PASS: load alone did NOT brown out or crash the rail.")
    emit("    Load is not the trigger.")
else:
    emit(" => Load alone affected the rail — investigate further.")
emit("=" * 60)
scope.close(); log.close()
