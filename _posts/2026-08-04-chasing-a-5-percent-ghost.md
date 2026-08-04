---
layout: post
title: "Chasing a 5% Ghost: When a Good Result Lies"
date: 2026-08-04 12:00:00 +0200
author: Eduardo Elias
reading_time: "12 min read"
description: >-
  How a fleet of Raspberry Pi Compute Modules taught me to distrust a passing
  test — a hardware brown-out detective story with an oscilloscope, a cellular
  modem, and one very tempting wrong answer.
tags: [raspberry-pi, hardware, iot, debugging, power-integrity]
---

Somewhere out in the field, about **5% of an 1800-unit Raspberry Pi CM3+ fleet**
would crash — but only after a very specific event: **losing and regaining their
4G connection.** When it happened, the unit often didn't just reboot. It became
*unusable*: powered but unreachable, sometimes stuck at the bootloader, needing
a technician to physically swap it.

Five percent. After a network blip. On otherwise-healthy hardware. This is the
story of chasing that ghost down to the millivolt — and of the moment a
beautiful, tempting fix turned out to be a lie.

## The shape of the problem

The symptoms formed an odd constellation:

- Only ~5% of units, seemingly at random.
- Always correlated with a **4G disconnect/reconnect**.
- After the crash: "powers up, nothing happens," or "stuck at boot with some
  numbers," or "takes forever, so we just swap it."

A power event doesn't care about your network state. A fault that fires
*specifically* on modem reconnection smells like software — or like something
electrical that the modem's radio activity triggers. The earliest clue was a
field power-meter capture showing the 3.3&nbsp;V rail briefly collapsing toward
**2.5&nbsp;V**. Suspicious. But a 1&nbsp;Hz power meter aliases fast transients,
and correlation isn't cause. I needed to reproduce it on the bench.

## Dead end #1: a healthy board refuses to break

I put a known-good board on the bench and hammered the modem: 100 radio
power-cycles, then full modem cold-reboots (`AT+CFUN=1,1`, which drops the
device off USB and re-enumerates it — the biggest inrush event you can ask a
modem for). I watched the 3.3&nbsp;V rail the whole time.

Nothing. Not a single dip below 3.2&nbsp;V. I stacked on CPU, memory, and USB
disk load. The rail sagged a *whopping* 70&nbsp;mV under everything I threw at
it. The good board's power delivery was, frankly, excellent.

That's a useful non-result: **the crash is not a generic design flaw.** If
every board did this, all 1800 would be dropping. Something separated the 5%
from the 95%.

## Building a rig that tells the truth

The power meter wasn't good enough. I moved to a **Digilent Analog Discovery 3**
— a USB oscilloscope with a scriptable SDK — driven from Python on macOS. (One
yak-shave worth noting: the WaveForms SDK couldn't find the device until I
symlinked the framework it ships inside the app bundle to where the runtime
expects it, `/Library/Frameworks/dwf.framework`. After that, headless capture
just worked.)

With two analog channels I could probe two rails at once and finally *map the
whole power tree* on the carrier board:

| Rail | Idle | Under load | Verdict |
|---|---|---|---|
| +12V input | 12.15 V | −31 mV | rock solid |
| +5V (USB/peripheral) | 5.02 V | −65 mV | load-sensitive |
| +5V standby | 5.03 V | ~0 mV | quiet |
| +3.3V (SoC/IO) | 3.42 V | steady | well-regulated |
| +1.2V (core/DDR) | 1.196 V | −6 mV | rock solid |
| +1.8V | 1.835 V | −21 mV | solid |

Every rail on the good board was healthy. The most load-sensitive point was the
+5V USB path — which is exactly where the cellular modem draws its current. A
clue, not a culprit. Yet.

> **Method.** Throughout, the measured quantity is the **minimum voltage** of a
> rail over a defined window, captured at 100&nbsp;kSa/s on the Analog Discovery
> (channel referenced to board ground at the rail's test point). The first
> acquisition buffer after each reconfigure is discarded to avoid a settling
> artefact. Every experiment compares a **treated** condition against a matched
> **control** on the *same* board, and the firmware under-voltage alarm
> (`hwmon .../in0_lcrit_alarm`) is logged alongside as an independent check.

## The breakthrough: an *aged* board

Then I swapped in an **older board** with the same CM3+ module, and measured the
same +3.3&nbsp;V rail at idle:

- Good board: **38 mV** of ripple.
- Aged board: **92 mV** of ripple — roughly **2.4× noisier**, and sitting
  ~50&nbsp;mV lower.

That's the fingerprint of **degraded decoupling** — aging capacitors and/or a
weaker regulator. And when I ran the exact same modem-reset test that the good
board shrugged off, the aged board behaved completely differently:

![Good board is immune; the aged board dips on every modem reset](/assets/chart-good-vs-aged.png)

*Seven of ten modem resets pulled the aged board's +3&nbsp;V rail down to
~3.0&nbsp;V — a 360&nbsp;mV dip — while the good board never moved.* The variable
was never the modem. It was **board aging.**

## The antenna: with vs. without

Here's a subtlety that matters, and it's the part I most want to compare
head-to-head. My bench modem initially had **no antenna** — it registered on no
network and, crucially, never transmitted. That means it never drew the big
**RF power-amplifier current** that a real, transmitting modem pulls when it
re-registers on a tower after a dropout.

So I ran the aged-board modem-reset test **twice**: once with no antenna, and
once with an antenna attached and the modem actually registered on a live
network (real RF-TX current during each reconnect).

![Antenna pushes the dips deeper](/assets/chart-antenna-vs-noantenna.png)

| Condition | Dips (of 10) | Worst +3V |
|---|---|---|
| Aged board, **no antenna** | 7 | 3.026 V |
| Aged board, **with antenna** | 7 | **3.012 V** |

The antenna consistently added **another 15–30&nbsp;mV of sag** on the deepest
cycles. On its own that sounds tiny — but it's directional and it's real: the
RF-TX registration burst is genuine extra load on the same weak rail, and it
reliably walks the minimum *down*, toward the edge. Without the antenna I could
characterize the mechanism; **with** the antenna I could see the last stressor
the field actually applies.

The no-antenna test is not a throwaway. It isolates the modem's *digital/USB*
inrush from its *RF* inrush. The gap between the grey and green traces above is,
quite literally, the current cost of talking to a cell tower — measured at the
rail.

## Isolating the variable: a controlled experiment

At this point I had a strong suspicion but not a clean proof. The honest
objection to everything above is *confounding*: the crashes happened when the
modem reset **and** the board was under load. Which one actually matters? To
answer that like a scientist, you hold everything constant and vary **one**
factor at a time.

So I designed two mutually-exclusive scenarios on the **same aged board**:

- **Scenario A — "load is not the problem."** Antenna **detached** (zero RF
  activity), **no modem reset**, but 10 minutes of heavy CPU + memory + I/O
  stress. If workload were the cause, this should sag the rail.
- **Scenario B — "the modem is the problem."** Antenna **attached** and
  registered, repeated modem disconnect/reconnect, but **no heavy load**. If the
  modem's RF consumption were the cause, this should sag the rail even with an
  idle CPU.

The primary metric is the same in both: the **minimum +3&nbsp;V** the rail
reaches, sampled continuously on the Analog Discovery. The prediction is a clean
dissociation — A stays flat, B dips.

![Load is harmless; every modem reconnect sags the rail](/assets/chart-load-vs-modem.png)

The result could not be more clear-cut:

| | Scenario A (load only) | Scenario B (modem reset) |
|---|---|---|
| Heavy CPU/IO load | yes | no |
| Antenna / RF reconnect | no | yes |
| Samples / cycles | 120 (10 min) | 30 |
| Dips below 3.2 V | **0** | **30 of 30 (100%)** |
| Mean +3V minimum | ~3.32 V | 3.06 V |
| Worst +3V | **3.314 V** | **2.851 V** |
| Crash | none | intermittent |

Ten minutes of maxing out every core plus hammering both the eMMC and an
external USB disk moved the rail by a few tens of millivolts — it never left
3.3&nbsp;V territory. Meanwhile **every single modem reconnect**, on an otherwise
idle CPU, pulled the rail hundreds of millivolts down, one cycle plunging to
**2.851&nbsp;V** — deep into the brown-out margin. Load is a red herring; the
modem's RF re-registration inrush is the trigger.

### The scripts

The whole experiment is small enough to share. A tiny library wraps the two
things I need: talk to the modem over its serial port, and read the rail minimum
off the Analog Discovery. Everything is parameterised by environment variables
(`DUT_SSH`, `DWF_LIB`) — no hosts, carriers, or paths baked in.

```python
# rail_monitor_lib.py — shared helpers (excerpt)
import os, time, ctypes, subprocess, base64

DUT_SSH = os.environ.get("DUT_SSH", "root@device.local")
DWF_LIB = os.environ.get("DWF_LIB", "/Library/Frameworks/dwf.framework/dwf")
AD3_CH  = int(os.environ.get("AD3_CHANNEL", "0"))
RATE, BUF, RANGE = 100_000, 8192, 10.0

def ssh(cmd, timeout=25):
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=8", DUT_SSH, cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return None

def alive():
    return ssh("echo UP", 10) == "UP"

# The modem's AT port can move across reboots, so probe for an "OK".
_ATPORT_PY = r'''import os, termios, time, select
def probe(p):
    try:
        fd = os.open(p, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(fd); a[0]=a[1]=a[3]=0
        a[4]=termios.B115200; a[5]=termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, a)
        os.write(fd, b"AT\r"); time.sleep(0.4)
        buf=b""; end=time.time()+1
        while time.time()<end:
            r,_,_=select.select([fd],[],[],0.2)
            if r:
                try: buf += os.read(fd, 64)
                except: break
        os.close(fd)
        return b"OK" in buf
    except: return False
for i in range(8):
    if probe("/dev/ttyUSB%d" % i):
        print("/dev/ttyUSB%d" % i); break
'''

def find_at_port():
    b64 = base64.b64encode(_ATPORT_PY.encode()).decode()
    return (ssh(f"echo {b64} | base64 -d | python3 -", 30) or "").strip() or None

def modem_reset(port):
    """Full modem reboot: disconnect + reconnect (the RF inrush event)."""
    b64 = base64.b64encode(
        b'import os,termios,time,sys\n'
        b'fd=os.open(sys.argv[1],os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)\n'
        b'a=termios.tcgetattr(fd);a[0]=a[1]=a[3]=0\n'
        b'a[4]=termios.B115200;a[5]=termios.B115200\n'
        b'termios.tcsetattr(fd,termios.TCSANOW,a)\n'
        b'os.write(fd,b"AT+CFUN=1,1\\r");time.sleep(1);os.close(fd)\n'
    ).decode()
    ssh(f"echo {b64} | base64 -d | python3 - {port}", 15)

class RailScope:
    """Read the +3V rail minimum from an Analog Discovery via the WaveForms SDK."""
    def __init__(self):
        self.dwf = ctypes.cdll.LoadLibrary(DWF_LIB)
        self.h = ctypes.c_int()
        self.dwf.FDwfDeviceOpen(-1, ctypes.byref(self.h))
        if not self.h.value:
            raise RuntimeError("AD3 open failed (close the WaveForms GUI first)")
        d, h = self.dwf, self.h
        d.FDwfAnalogInChannelEnableSet(h, AD3_CH, 1)
        d.FDwfAnalogInChannelRangeSet(h, AD3_CH, ctypes.c_double(RANGE))
        d.FDwfAnalogInFrequencySet(h, ctypes.c_double(RATE))
        d.FDwfAnalogInBufferSizeSet(h, BUF)
        self.sts = ctypes.c_byte(); self.rg = (ctypes.c_double * BUF)()

    def min_over(self, seconds):
        d, h = self.dwf, self.h
        t0 = time.time(); mn = 99.0; first = True
        while time.time() - t0 < seconds:
            d.FDwfAnalogInConfigure(h, 1, 1)
            while True:
                d.FDwfAnalogInStatus(h, 1, ctypes.byref(self.sts))
                if self.sts.value == 2: break
                time.sleep(0.0003)
            d.FDwfAnalogInStatusData(h, AD3_CH, self.rg, BUF)
            if first: first = False; continue   # discard settling buffer
            mn = min(mn, min(self.rg))
        return mn
```

**Scenario A** is then just: start the load, sample the rail, and never touch
the modem.

```python
# scenario_a_load_only.py (core)
import time, rail_monitor_lib as rl
BROWNOUT = 2.90

scope = rl.RailScope()
rl.push_load_helper()
loadp = rl.start_cpu_load()          # 4 cores, performance governor
iop   = rl.start_io_load()           # sustained dd write+read loop
worst, crashed, t_end = 99.0, False, time.time() + 10*60
while time.time() < t_end:
    mn = scope.min_over(5)
    worst = min(worst, mn)
    if not rl.alive():
        crashed = True; break
print(f"worst +3V = {worst:.3f} V, crashed = {crashed}")
# => 3.314 V, False  — load alone is not the trigger
```

**Scenario B** is the mirror image: no load, just reconnect the modem and watch.

```python
# scenario_b_modem_reset.py (core)
import time, rail_monitor_lib as rl
scope = rl.RailScope()
dips, worst = 0, 99.0
for i in range(30):
    port = rl.find_at_port()         # re-detect; it moves across resets
    rl.modem_reset(port)             # disconnect + reconnect -> RF inrush
    mn = scope.min_over(6)           # capture the reconnect window
    worst = min(worst, mn)
    if mn < 3.20: dips += 1
    if not rl.alive():
        # brown-out crash: wait for auto-recovery (or cold power cycle)
        while not rl.alive(): time.sleep(5)
print(f"dips = {dips}/30, worst +3V = {worst:.3f} V")
# => 30/30 dips, 2.851 V — the modem reconnect is the trigger
```

That's the entire proof: two short scripts, one variable each, a clean
dissociation. The full, runnable versions live in the repo.

## Reproducing the crash

One dip alone still wasn't enough to crash the bench unit; it hovered around
3.0&nbsp;V, marginal but alive. The field, though, doesn't apply one stressor at
a time. So I stacked them: heavy CPU + memory load running continuously, antenna
attached, and back-to-back modem resets on top.

![Stacking stressors walks the rail into the crash zone](/assets/chart-escalation.png)

That did it. The +3&nbsp;V rail brown-out to **2.858&nbsp;V** — and the board
went unreachable. A hard crash. The serial console told the rest of the story:
the kernel log simply **stopped mid-line** — no panic, no clean shutdown, just
an instantaneous cutoff. That's the signature of a **brown-out reset**, not a
software fault.

And then it got interesting. The serial console showed a service starting up
during recovery:

```
health-watchdog.service - Userspace health watchdog (reboots on brown-out zombie state)
```

The team had *already met this ghost.* Reading the script, it documents the
exact failure mode in its own comments: during a brown-out, the kernel and PID&nbsp;1
stay alive (so the hardware watchdog keeps getting petted and never fires) while
**the eMMC access path dies.** Every disk read and every SSH login then fails —
the unit is a *zombie*: powered, "up," but functionally dead. That is the field's
"powers up, nothing happens." On the next reset I even caught it **halted at the
GRUB menu**, waiting for a keypress that, in the field, no one is there to press.

The whole chain, reproduced end to end:

> aged board → weak, noisy +3&nbsp;V rail → 4G reconnect RF-TX inrush + SoC load
> → +3&nbsp;V brown-out below ~2.8&nbsp;V → eMMC path dies while the kernel lives
> → "zombie" / GRUB halt → **"unusable, swap it."**

## The tempting fix — and the lie

Here's the idea that felt brilliant. If the damage is the eMMC getting hit
*mid-write* during the brown-out, what if we **quiesce the eMMC during the exact
risky window** — freeze the filesystem right before dialing the modem, hold
through the inrush, then thaw?

It's clean, it's software-only, and `fsfreeze` is built for exactly this kind of
consistency window. I verified the modem still dials fine while `/var` is frozen
(the AT path is serial, no disk needed), wrapped it in a script with a hard
safety-timeout auto-thaw, and ran it under the same crash-inducing load.

**Twenty cycles. Zero crashes.** Where the unprotected board had crashed by
cycle 4, the protected one sailed through. I was ready to call it.

Then I did the thing you're supposed to do with a *probabilistic* failure:
a controlled, interleaved **A/B soak** — protected and unprotected dials
alternating under identical load, randomized order, enough cycles to mean
something.

![The A/B soak refutes the eMMC-freeze fix](/assets/chart-ab-soak.png)

| Arm | Cycles | Deep dips | Crashes |
|---|---|---|---|
| Unprotected (eMMC live) | 18 | 1 | **0** |
| Protected (eMMC frozen) | 18 | 1 | **2** |

The *protected* arm crashed. Twice. The unprotected arm didn't crash at all.

My beautiful 20-for-20 run had been **luck**, not causation. Once I gathered a
fair sample, the mitigation evaporated — because it was aimed at the wrong
layer. At ~2.8&nbsp;V the **SoC core itself** brown-outs; the CPU and RAM lose
voltage. You cannot protect a processor from losing power by freezing a
filesystem. The eMMC "zombie" is a *consequence* of the brown-out, not its
cause.

## What was actually true

The root cause is **electrical, not software**: aged +3&nbsp;V decoupling on a
subset of boards lets the modem-reconnect inrush (worse with a real transmitting
antenna, worse still under load) drag the rail below the SoC's brown-out
threshold. The only reliable fix lives in hardware — restore the +3&nbsp;V margin
with bulk/decoupling capacitance or a stronger regulator so the rail never
reaches the danger zone.

Software can *reduce* corruption and *automate* recovery, but it cannot prevent a
processor brown-out. And there's a bonus: because aging shows up as **elevated
idle ripple** (~90&nbsp;mV vs ~38&nbsp;mV), you can *screen* boards and replace
the risky ones **before** they fail in the field, instead of after.

## The lesson I'm keeping

The eMMC-freeze idea taught me more than the fix would have. For a probabilistic
failure, **a single passing run is not evidence** — it's an anecdote wearing a
lab coat. It took a boring, controlled A/B to separate a real effect from a
lucky streak, and it saved a wrong fix from shipping to 1800 devices.

Measure the rail. Distrust the good result. Chase the ghost all the way down.

## The code

The experiment is deliberately small and dependency-free so anyone can adapt it
to their own board. All host/carrier/path specifics are read from environment
variables (`DUT_SSH`, `DWF_LIB`), so nothing device-specific is baked in.

- [`rail_monitor_lib.py`](/code/rail_monitor_lib.py) — shared helpers: SSH,
  modem AT control (auto-detecting the port across reboots), and the
  `RailScope` wrapper around the WaveForms SDK.
- [`scenario_a_load_only.py`](/code/scenario_a_load_only.py) — the load-only
  control (no modem reset).
- [`scenario_b_modem_reset.py`](/code/scenario_b_modem_reset.py) — the
  modem-reconnect treatment (no heavy load).
- [`diag_load.py`](/code/diag_load.py) — the CPU + memory load generator.

Wiring: Analog Discovery **CH1 (1+)** on the +3&nbsp;V test point, **1−** and
ground on board GND. Run with the WaveForms GUI closed (only one process can own
the device), point `DUT_SSH` at your board, and the two scenarios reproduce the
dissociation above.

*This write-up anonymises internal hostnames, addresses, the carrier, and
proprietary service names; the electrical findings and methodology are
presented as-is.*
