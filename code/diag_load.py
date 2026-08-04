#!/usr/bin/env python3
"""
diag_load.py — simple, dependency-free CPU + memory load generator.

Runs `ncpu` busy-loop workers (FPU + integer) plus one memory-bandwidth hog
(dd zero -> null) for `seconds`. Used as the "load" treatment in the
load-vs-modem experiment. Copy to the device and run:

    python3 diag_load.py <ncpu> <seconds>
"""
import os, sys, time, subprocess

ncpu = int(sys.argv[1])
dur = float(sys.argv[2])
end = time.time() + dur
kids = []


def burn(stop):
    x = 1.1
    while time.time() < stop:
        for _ in range(20000):
            x = (x * 1.0000001 + 2.72) ** 0.5 + (x % 3.14)


for _ in range(ncpu):
    p = os.fork()
    if p == 0:
        burn(end)
        os._exit(0)
    kids.append(p)

# one memory-bandwidth worker
p = os.fork()
if p == 0:
    while time.time() < end:
        subprocess.run("dd if=/dev/zero of=/dev/null bs=1M count=800",
                       shell=True, stderr=subprocess.DEVNULL)
    os._exit(0)
kids.append(p)

for k in kids:
    os.waitpid(k, 0)
