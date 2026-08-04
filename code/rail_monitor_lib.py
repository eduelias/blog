#!/usr/bin/env python3
"""
rail_monitor_lib.py — Shared helpers for CM3+ rail brown-out experiments.

Publishable / anonymizable: no hardcoded hosts, IPs, carriers, or paths.
All device access is via SSH to a target given by env or CLI. The Analog
Discovery (AD3) is accessed through the WaveForms SDK on the host.

Environment variables (override defaults):
  DUT_SSH        SSH target for the device under test   (e.g. root@device.local)
  DWF_LIB        Path to the WaveForms dwf library
  AD3_CHANNEL    Analog-in channel index for the +3V rail probe (default 0)

Wiring: AD3 CH1 (1+) -> +3V test point, (1-) and GND -> board GND.
"""
import os, time, ctypes, subprocess

DUT_SSH   = os.environ.get("DUT_SSH", "root@device.local")
DWF_LIB   = os.environ.get(
    "DWF_LIB",
    "/Library/Frameworks/dwf.framework/dwf",  # macOS default
)
AD3_CH    = int(os.environ.get("AD3_CHANNEL", "0"))
RATE, BUF, RANGE = 100000, 8192, 10.0


# ---------------- SSH helpers ----------------
def ssh(cmd, timeout=25):
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=8", DUT_SSH, cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return None


def ssh_bg(cmd):
    return subprocess.Popen(["ssh", "-o", "ConnectTimeout=8", DUT_SSH, cmd],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def alive():
    return ssh("echo UP", 10) == "UP"


# ---------------- Modem (cellular) helpers ----------------
_ATPORT_PY = r'''import os, termios, time, select
def probe(p):
    try:
        fd=os.open(p, os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
        a=termios.tcgetattr(fd); a[0]=0;a[1]=0;a[3]=0
        a[4]=termios.B115200; a[5]=termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, a)
        os.write(fd, b"AT\r"); time.sleep(0.4)
        buf=b""; end=time.time()+1
        while time.time()<end:
            r,_,_=select.select([fd],[],[],0.2)
            if r:
                try: buf+=os.read(fd,64)
                except: break
        os.close(fd)
        return b"OK" in buf
    except: return False
for i in range(8):
    p="/dev/ttyUSB%d" % i
    if probe(p):
        print(p); break
'''

def find_at_port():
    """Auto-detect the cellular modem's AT command port.

    The enumeration order can change across reboots, so we probe each
    USB-serial port for an 'OK' response to a bare 'AT'.
    """
    b64 = __import__("base64").b64encode(_ATPORT_PY.encode()).decode()
    return (ssh(f"echo {b64} | base64 -d | python3 -", 30) or "").strip() or None


_AT_PY = r'''import os, termios, time, sys
port, atcmd, settle = sys.argv[1], sys.argv[2], float(sys.argv[3])
fd=os.open(port, os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
a=termios.tcgetattr(fd); a[0]=0;a[1]=0;a[3]=0
a[4]=termios.B115200; a[5]=termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)
os.write(fd, (atcmd+"\r").encode()); time.sleep(settle); os.close(fd)
'''

def modem_at(port, at_cmd, settle=1.0):
    """Send a single AT command to the modem over its serial port."""
    b64 = __import__("base64").b64encode(_AT_PY.encode()).decode()
    ssh(f"echo {b64} | base64 -d | python3 - {port} '{at_cmd}' {settle}", 15)


def modem_reset(port):
    """Full modem reboot (disconnect + reconnect). Triggers the RF
    re-registration inrush when an antenna is attached."""
    modem_at(port, "AT+CFUN=1,1", settle=1.0)


_SIGNAL_PY = r'''import os, termios, time, select, sys
port=sys.argv[1]
fd=os.open(port, os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
a=termios.tcgetattr(fd); a[0]=0;a[1]=0;a[3]=0
a[4]=termios.B115200; a[5]=termios.B115200
termios.tcsetattr(fd, termios.TCSANOW, a)
def cmd(c,w=1.2):
    os.write(fd,(c+"\r").encode()); b=b""; e=time.time()+w
    while time.time()<e:
        r,_,_=select.select([fd],[],[],0.2)
        if r:
            try: b+=os.read(fd,128)
            except: break
    return b.decode(errors="replace").replace("\r"," ").replace("\n"," ").strip()
print(cmd("AT+CSQ"), "|", cmd("AT+CREG?"))
os.close(fd)
'''

def modem_signal(port):
    """Return raw AT+CSQ / AT+CREG strings for logging antenna/registration."""
    b64 = __import__("base64").b64encode(_SIGNAL_PY.encode()).decode()
    out = ssh(f"echo {b64} | base64 -d | python3 - {port}", 15)
    return out or "n/a"


# ---------------- Load helpers ----------------
LOAD_SRC = os.path.join(os.path.dirname(__file__), "diag_load.py")


def push_load_helper():
    """Copy the CPU+memory load generator to the device (idempotent)."""
    subprocess.run(["scp", "-o", "ConnectTimeout=10", LOAD_SRC,
                    f"{DUT_SSH}:/tmp/diag_load.py"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_cpu_load(cores=4, seconds=99999):
    ssh("for c in 0 1 2 3; do echo performance > "
        "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor 2>/dev/null; done")
    return ssh_bg(f"pkill -f diag_load.py 2>/dev/null; "
                  f"python3 /tmp/diag_load.py {cores} {seconds}")


def stop_cpu_load():
    ssh("pkill -f diag_load.py 2>/dev/null; "
        "for c in 0 1 2 3; do echo schedutil > "
        "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor 2>/dev/null; done")


def start_io_load(path="/var/tmp/.railtest_io.bin", mb=256):
    """Sustained write+read loop on the given filesystem path."""
    return ssh_bg(
        f"while true; do dd if=/dev/zero of={path} bs=1M count={mb} "
        f"conv=fsync 2>/dev/null; sync; "
        f"dd if={path} of=/dev/null bs=1M 2>/dev/null; done")


def stop_io_load(path="/var/tmp/.railtest_io.bin"):
    ssh(f"pkill -f 'dd if' 2>/dev/null; rm -f {path}; sync")


def hw_undervoltage():
    """Firmware brown-out alarm (1 = under-voltage seen)."""
    return ssh("cat /sys/class/hwmon/hwmon0/in0_lcrit_alarm 2>/dev/null", 8)


# ---------------- AD3 rail sampling ----------------
class RailScope:
    def __init__(self):
        self.dwf = ctypes.cdll.LoadLibrary(DWF_LIB)
        self.h = ctypes.c_int()
        self.dwf.FDwfDeviceOpen(-1, ctypes.byref(self.h))
        if not self.h.value:
            e = ctypes.create_string_buffer(512)
            self.dwf.FDwfGetLastErrorMsg(e)
            raise RuntimeError("AD3 open failed (close WaveForms GUI?): "
                               + e.value.decode())
        d, h = self.dwf, self.h
        d.FDwfAnalogInChannelEnableSet(h, AD3_CH, 1)
        d.FDwfAnalogInChannelRangeSet(h, AD3_CH, ctypes.c_double(RANGE))
        d.FDwfAnalogInChannelOffsetSet(h, AD3_CH, ctypes.c_double(0.0))
        d.FDwfAnalogInFrequencySet(h, ctypes.c_double(RATE))
        d.FDwfAnalogInBufferSizeSet(h, BUF)
        self.sts = ctypes.c_byte()
        self.rg = (ctypes.c_double * BUF)()

    def min_over(self, seconds):
        """Return the minimum rail voltage observed over `seconds`."""
        d, h = self.dwf, self.h
        t0 = time.time(); mn = 99.0; first = True
        while time.time() - t0 < seconds:
            d.FDwfAnalogInConfigure(h, 1, 1)
            while True:
                d.FDwfAnalogInStatus(h, 1, ctypes.byref(self.sts))
                if self.sts.value == 2:
                    break
                time.sleep(0.0003)
            d.FDwfAnalogInStatusData(h, AD3_CH, self.rg, BUF)
            if first:      # discard first buffer (settling)
                first = False; continue
            a = min(self.rg)
            if a < mn:
                mn = a
        return mn

    def close(self):
        self.dwf.FDwfDeviceClose(self.h)
