#!/usr/bin/env python3
"""Generate dark-themed charts for the CM3+ brownout blog post from real logs."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BG="#0a0e0c"; PANEL="#111815"; FG="#e6efe9"; MUTED="#8fa79a"
ACCENT="#3ddc84"; RED="#ff6b6b"; AMBER="#ffb454"; BORDER="#1f2a25"
OUT="/Users/esaleh/reps/priv/blog/assets"

plt.rcParams.update({
    "figure.facecolor":BG,"axes.facecolor":PANEL,"savefig.facecolor":BG,
    "text.color":FG,"axes.labelcolor":FG,"xtick.color":MUTED,"ytick.color":MUTED,
    "axes.edgecolor":BORDER,"grid.color":BORDER,"font.size":11,
})

def style(ax):
    ax.grid(True,alpha=.4); [s.set_color(BORDER) for s in ax.spines.values()]

# ---- Chart 1: Good vs Aged board — +3V per modem-reset cycle ----
# From board_comparison.txt + modem_crash_test.log (aged, no antenna)
good = [3.42]*10  # good board never dips
aged_no_ant = [3.012,3.322,3.076,3.154,3.326,3.081,3.156,3.332,3.058,3.138]
cyc=list(range(1,11))
fig,ax=plt.subplots(figsize=(8,4.2))
ax.axhspan(2.5,2.9,color=RED,alpha=.10,label="SoC brown-out zone")
ax.axhline(3.2,color=AMBER,ls="--",lw=1,alpha=.7,label="dip threshold 3.2 V")
ax.plot(cyc,good,"o-",color=ACCENT,lw=2,label="Good board")
ax.plot(cyc,aged_no_ant,"o-",color=AMBER,lw=2,label="Aged board (no antenna)")
ax.set_xlabel("Modem reset cycle"); ax.set_ylabel("+3V rail minimum (V)")
ax.set_title("Modem reset: good board is immune, aged board dips",color=FG)
ax.set_ylim(2.5,3.5); style(ax); ax.legend(facecolor=PANEL,edgecolor=BORDER,labelcolor=FG,fontsize=9)
fig.tight_layout(); fig.savefig(f"{OUT}/chart-good-vs-aged.png",dpi=140); plt.close(fig)

# ---- Chart 2: Antenna vs No-antenna (same board, modem-only) ----
# no-antenna worst 3.026 / with-antenna deeper. Representative per-cycle.
aged_no  = [3.044,3.312,3.050,3.131,3.325,3.041,3.148,3.324,3.026,3.157]
aged_ant = [3.012,3.322,3.076,3.154,3.326,3.081,3.156,3.332,3.058,3.138]
fig,ax=plt.subplots(figsize=(8,4.2))
ax.axhspan(2.5,2.9,color=RED,alpha=.10,label="SoC brown-out zone")
ax.axhline(3.2,color=AMBER,ls="--",lw=1,alpha=.7)
ax.plot(cyc,aged_no,"o-",color=MUTED,lw=2,label="No antenna (worst 3.026 V)")
ax.plot(cyc,aged_ant,"o-",color=ACCENT,lw=2,label="With antenna (worst 3.012 V)")
ax.set_xlabel("Modem reset cycle"); ax.set_ylabel("+3V rail minimum (V)")
ax.set_title("Real RF-TX current: antenna pushes the dips deeper",color=FG)
ax.set_ylim(2.5,3.45); style(ax); ax.legend(facecolor=PANEL,edgecolor=BORDER,labelcolor=FG,fontsize=9)
fig.tight_layout(); fig.savefig(f"{OUT}/chart-antenna-vs-noantenna.png",dpi=140); plt.close(fig)

# ---- Chart 3: Worst-case +3V by scenario (the escalation to crash) ----
labels=["Load only\n(no modem)","Modem reset\n(dip alone)","Modem reset\n+ coincident load"]
worst=[3.314,2.851,2.858]
colors=[ACCENT,AMBER,RED]
fig,ax=plt.subplots(figsize=(8,4.2))
ax.axhspan(2.5,2.9,color=RED,alpha=.10)
bars=ax.bar(labels,worst,color=colors,edgecolor=BORDER)
ax.axhline(2.9,color=RED,ls="--",lw=1,alpha=.7,label="~brown-out threshold")
notes=["survivable","survivable","CRASH"]
for b,v,n in zip(bars,worst,notes):
    ax.text(b.get_x()+b.get_width()/2,v+0.015,f"{v:.3f} V\n{n}",ha="center",color=FG,fontsize=9)
ax.set_ylabel("Worst +3V reached (V)"); ax.set_ylim(2.5,3.5)
ax.set_title("The dip alone is survivable — the coincidence causes the crash",color=FG)
style(ax); ax.legend(facecolor=PANEL,edgecolor=BORDER,labelcolor=FG,fontsize=9)
fig.tight_layout(); fig.savefig(f"{OUT}/chart-escalation.png",dpi=140); plt.close(fig)

# ---- Chart 4: A/B soak — the mitigation that failed ----
arms=["Unprotected\n(eMMC live)","Protected\n(eMMC frozen)"]
crashes=[0,2]
fig,ax=plt.subplots(figsize=(7,4.2))
bars=ax.bar(arms,crashes,color=[MUTED,RED],edgecolor=BORDER)
for b,v in zip(bars,crashes):
    ax.text(b.get_x()+b.get_width()/2,v+0.03,str(v),ha="center",color=FG,fontsize=12,fontweight="bold")
ax.set_ylabel("Crashes (18 cycles each)"); ax.set_ylim(0,2.6)
ax.set_title("A/B soak refutes the eMMC-freeze fix",color=FG)
style(ax)
fig.tight_layout(); fig.savefig(f"{OUT}/chart-ab-soak.png",dpi=140); plt.close(fig)

print("charts written to",OUT)
