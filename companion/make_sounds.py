"""Synthesizes the dashboard's sound set into web/sounds/*.wav.

The WAV files ship with the app, so you never need to run this. It's here so
the sounds can be tweaked and rebuilt: `py -3 make_sounds.py`.
Standard library only.
"""
import math
import os
import random
import struct
import wave

SR = 24000
MAX_LEN = 0.8  # seconds: spools and echoes stay short; nothing loops
TS = 1.0        # time scale; long recipes are squeezed to fit MAX_LEN
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "sounds")
rnd = random.Random(7)


def n_of(sec):
    return max(1, int(sec * TS * SR))


def sweep(f0, f1, i, n):
    """Exponential frequency glide from f0 to f1 over n samples."""
    return f0 * (f1 / f0) ** (i / max(1, n - 1))


def osc(kind, f0, f1, dur, detune=0.0):
    n, out, ph = n_of(dur), [], 0.0
    for i in range(n):
        f = sweep(f0, f1, i, n) * (1 + detune)
        ph = (ph + f / SR) % 1.0
        if kind == "sine":
            v = math.sin(2 * math.pi * ph)
        elif kind == "saw":
            v = 2 * ph - 1
        elif kind == "square":
            v = 1.0 if ph < .5 else -1.0
        else:  # triangle
            v = 4 * abs(ph - .5) - 1
        out.append(v)
    return out


def noise(dur):
    return [rnd.uniform(-1, 1) for _ in range(n_of(dur))]


def lowpass(sig, c0, c1=None):
    """One-pole lowpass whose cutoff glides from c0 to c1 Hz."""
    c1 = c1 or c0
    out, y, n = [], 0.0, len(sig)
    for i, x in enumerate(sig):
        a = 1 - math.exp(-2 * math.pi * sweep(c0, c1, i, n) / SR)
        y += a * (x - y)
        out.append(y)
    return out


def highpass(sig, c):
    lp = lowpass(sig, c)
    return [x - y for x, y in zip(sig, lp)]


def env(sig, a=0.005, curve=4.0, hold=0.0):
    """Fast attack, optional hold, then exponential-ish decay to silence."""
    n, na, nh = len(sig), n_of(a), n_of(hold)
    out = []
    for i, x in enumerate(sig):
        if i < na:
            g = i / na
        elif i < na + nh:
            g = 1.0
        else:
            t = (i - na - nh) / max(1, n - na - nh)
            g = (1 - t) ** curve
        out.append(x * g)
    return out


def swell(sig, rise=0.6, curve=2.0):
    """Ramp up for `rise` of the length, then fall away."""
    n, out = len(sig), []
    for i, x in enumerate(sig):
        t = i / n
        g = (t / rise) ** curve if t < rise else ((1 - t) / (1 - rise)) ** 1.5
        out.append(x * g)
    return out


def trem(sig, rate, depth=.5):
    return [x * (1 - depth + depth * (0.5 + 0.5 * math.sin(2 * math.pi * rate * i / SR))) for i, x in enumerate(sig)]


def gain(sig, g):
    return [x * g for x in sig]


def mix(*parts):
    """parts: (signal, offset_seconds) or signal."""
    parts = [p if isinstance(p, tuple) else (p, 0) for p in parts]
    n = max(n_of(off) + len(s) for s, off in parts)
    out = [0.0] * n
    for s, off in parts:
        o = n_of(off) if off else 0
        for i, x in enumerate(s):
            out[o + i] += x
    return out


def echo(sig, delay=0.12, fb=0.38, wet=0.45, tail=0.5, damp=3500):
    """Feedback delay with a darkening repeat: the 'space' in the sounds."""
    d = n_of(delay)
    n = len(sig) + n_of(tail)
    dry = sig + [0.0] * (n - len(sig))
    buf, out, y = [0.0] * n, [0.0] * n, 0.0
    a = 1 - math.exp(-2 * math.pi * damp / SR)
    for i in range(n):
        tap = buf[i - d] if i >= d else 0.0
        y += a * (tap - y)
        buf[i] = dry[i] + y * fb
        out[i] = dry[i] + y * wet
    return out


def bell(f, dur=0.5, g=1.0):
    """Glassy chime: a few inharmonic partials with long decay."""
    return gain(mix(env(osc("sine", f, f, dur), .002, 3),
                    gain(env(osc("sine", f * 2.76, f * 2.76, dur * .6), .002, 4), .35),
                    gain(env(osc("sine", f * 5.4, f * 5.4, dur * .3), .002, 5), .15)), g)


def thud(f=60, dur=0.25, g=1.0):
    return gain(mix(env(osc("sine", f * 2, f, dur), .002, 3),
                    gain(env(lowpass(noise(.05), 900), .001, 2), .6)), g)


def relay(g=.5):
    return gain(env(highpass(noise(.012), 2000), .0005, 2), g)


def hiss(dur, c0=5000, c1=1200, g=.5):
    return gain(env(lowpass(noise(dur), c0, c1), .01, 2), g)


def blip(f, dur=.05, kind="sine", g=1.0):
    return gain(env(osc(kind, f, f, dur), .002, 2), g)


def chirp(f0, f1, dur=.07, kind="sine", g=1.0):
    return gain(env(osc(kind, f0, f1, dur), .003, 2), g)


def spool(f0, f1, dur, c0, c1, rising=True):
    body = mix(lowpass(osc("saw", f0, f1, dur), c0, c1),
               gain(lowpass(osc("saw", f0, f1, dur, .006), c0, c1), .8),
               gain(osc("sine", f0 * 2, f1 * 2, dur), .5))
    return swell(body, .75 if rising else .08, 1.6 if rising else 1)


S = {}
# --- general UI ---
S["click"] = lambda: echo(mix(chirp(2300, 1700, .03, g=.7), chirp(1150, 1000, .045, "triangle", .4)), .07, .25, .3, .2)
S["tab"] = lambda: echo(mix(gain(swell(lowpass(noise(.16), 700, 4200), .5), .5), chirp(600, 900, .08, g=.35)), .08, .2, .25, .2)
S["tick"] = lambda: echo(blip(900, .025, "triangle", .8), .06, .2, .2, .12)
S["deny"] = lambda: mix(lowpass(env(osc("square", 170, 140, .1), .002, 1.5), 1400), (lowpass(env(osc("square", 150, 120, .12), .002, 1.5), 1400), .12))
S["step_up"] = lambda: echo(chirp(900, 1250, .05, g=.8), .07, .25, .3, .2)
S["step_down"] = lambda: echo(chirp(1250, 900, .05, g=.8), .07, .25, .3, .2)
S["toggle_on"] = lambda: echo(mix(relay(), (chirp(880, 1320, .05), .006), (blip(1320, .07, g=.6), .055)), .1, .3, .35, .3)
S["toggle_off"] = lambda: echo(mix(relay(), (chirp(1320, 880, .05), .006), (blip(880, .07, g=.6), .055)), .1, .3, .35, .3)
S["mode_on"] = lambda: echo(mix(chirp(500, 1300, .14, g=.7), (bell(1300, .35, .5), .1)), .13, .35, .45, .5)
S["mode_off"] = lambda: echo(mix(chirp(1300, 500, .14, g=.7), (bell(650, .3, .4), .1)), .13, .35, .45, .4)

# --- power ---
def pwr(f0, f1, c0, c1):
    return echo(mix(env(lowpass(mix(osc("saw", f0, f1, .15), osc("saw", f0, f1, .15, .008)), c0, c1), .005, 2),
                    gain(env(osc("sine", f0 * 2, f1 * 2, .15), .005, 2), .6)), .11, .32, .4, .35)
S["pwr_up"] = lambda: pwr(300, 520, 900, 3800)
S["pwr_down"] = lambda: pwr(520, 300, 3800, 700)
S["pwr_max"] = lambda: echo(mix(spool(260, 620, .3, 600, 4500), (bell(1240, .5, .5), .26), (bell(1860, .5, .3), .3)), .12, .35, .45, .5)
S["pwr_min"] = lambda: echo(mix(spool(620, 180, .35, 4000, 400, False), (thud(55, .25, .7), .3)), .12, .3, .4, .4)
S["sys_on"] = lambda: echo(spool(70, 380, .6, 300, 4200), .14, .35, .4, .5)
S["sys_off"] = lambda: echo(spool(380, 50, .7, 4000, 250, False), .14, .3, .35, .4)
S["master_on"] = lambda: echo(mix(thud(45, .5, .9), (spool(55, 330, .9, 200, 4500), .05),
                                  (bell(523, .5, .35), .75), (bell(784, .5, .35), .85), (bell(1046, .7, .4), .95)), .15, .38, .45, .7)
S["master_off"] = lambda: echo(mix(spool(330, 40, 1.0, 4500, 150, False), (thud(40, .5, .9), .85)), .15, .3, .4, .5)
S["reset"] = lambda: echo(mix(chirp(1000, 400, .12, g=.6), (chirp(400, 800, .16, g=.6), .14), (bell(800, .4, .4), .28)), .12, .3, .4, .4)

# --- flight ---
S["boot"] = lambda: echo(mix(gain(swell(lowpass(osc("saw", 55, 110, 1.1), 200, 1500), .5), .5),
                             *[(bell(f, .45, .45), .12 * k) for k, f in enumerate((440, 660, 880, 1320))]), .14, .38, .45, .7)
S["quantum"] = lambda: echo(mix(gain(swell(osc("sine", 40, 110, 1.4), .7), .9),
                                gain(spool(55, 220, 1.4, 150, 2500), .7),
                                gain(swell(osc("sine", 1800, 4200, 1.4), .85, 3), .12)), .18, .45, .5, 1.0)
S["spool_down"] = lambda: echo(mix(gain(swell(osc("sine", 110, 40, 1.0), .05), .8), gain(spool(220, 50, 1.0, 2500, 150, False), .6)), .16, .4, .45, .7)
S["brake"] = lambda: echo(mix(*[(gain(env(lowpass(noise(.12), 3500, 900), .002, 2), .7), .1 * k) for k in range(3)],
                              gain(env(osc("sine", 120, 60, .35), .01, 2), .5)), .1, .3, .35, .4)
S["lights"] = lambda: echo(mix(relay(.6), (gain(env(osc("sine", 120, 120, .25), .01, 2), .4), .01), (bell(2600, .25, .25), .02)), .1, .3, .35, .3)
S["gear_down"] = lambda: echo(mix(gain(trem(lowpass(osc("saw", 110, 75, .8), 700), 22, .35), .6), hiss(.8, 3000, 1500, .25),
                                  (thud(55, .3, 1), .78), (relay(.5), .8)), .11, .25, .3, .35)
S["gear_up"] = lambda: echo(mix(gain(trem(lowpass(osc("saw", 75, 115, .8), 700), 22, .35), .6), hiss(.8, 1500, 3000, .25),
                                (thud(70, .25, .8), .78), (relay(.5), .8)), .11, .25, .3, .35)
S["servo"] = lambda: echo(gain(swell(lowpass(mix(osc("saw", 260, 420, .3), osc("saw", 262, 424, .3)), 1600), .5, 1), .6), .09, .25, .3, .25)
S["door"] = lambda: echo(mix(hiss(.45, 6000, 1500, .55), (thud(65, .2, .7), .38)), .1, .25, .3, .3)
S["comms"] = lambda: echo(mix(gain(env(lowpass(noise(.06), 3000), .001, 2), .3),
                              *[(blip(f, .045, "square", .25), .055 * k) for k, f in enumerate((900, 1200, 900, 1500))]), .12, .35, .45, .5)
S["autoland"] = lambda: echo(mix(*[(bell(f, .45, .45), .14 * k) for k, f in enumerate((1320, 990, 660))], (thud(50, .3, .5), .45)), .14, .38, .45, .6)

# --- combat ---
S["decoy"] = lambda: echo(mix(*[(mix(gain(env(lowpass(noise(.05), 4000), .001, 3), .8), chirp(500, 140, .09, g=.7)), .09 * k) for k in range(3)],
                              gain(swell(lowpass(noise(.5), 5000, 800), .2), .25)), .12, .35, .4, .5)
S["noise_field"] = lambda: echo(mix(gain(swell(lowpass(noise(.8), 7000, 900), .15), .5),
                                    gain(trem(env(osc("saw", 90, 70, .8), .02, 1.5), 37, .8), .25)), .15, .4, .45, .6)
S["missile_arm"] = lambda: echo(mix(lowpass(blip(1500, .05, "square", .45), 4000), (lowpass(blip(1500, .05, "square", .45), 4000), .08),
                                    (lowpass(blip(2000, .08, "square", .4), 4000), .16)), .09, .3, .35, .3)
S["missile_reset"] = lambda: echo(mix(lowpass(blip(1200, .05, "square", .4), 3500), (lowpass(blip(800, .08, "square", .4), 3500), .08)), .09, .3, .35, .3)
S["target"] = lambda: echo(mix(blip(1250, .05), (blip(1875, .06, g=.6), .06)), .1, .35, .4, .4)
S["ping"] = lambda: echo(mix(gain(env(osc("sine", 1100, 1050, .7), .002, 3), .9), gain(env(osc("sine", 2210, 2100, .4), .002, 4), .25)), .22, .5, .55, 1.4, 2500)
S["scan"] = lambda: echo(mix(gain(swell(osc("sine", 380, 2400, .45), .7), .7), gain(swell(osc("triangle", 760, 4800, .45), .7), .15)), .13, .4, .45, .6)
S["pin"] = lambda: echo(blip(990, .06, g=.8), .08, .3, .35, .25)

# --- mining / salvage ---
S["laser_on"] = lambda: echo(mix(gain(swell(osc("sine", 300, 1800, .35), .9, 1.5), .6),
                                 gain(swell(lowpass(osc("saw", 150, 900, .35), 600, 5000), .9, 1.5), .4),
                                 (gain(env(trem(lowpass(mix(osc("saw", 900, 880, .45), osc("saw", 906, 886, .45)), 3500), 31, .6), .01, 2.5), .55), .33)), .12, .35, .4, .5)
S["laser_off"] = lambda: echo(mix(gain(env(osc("sine", 1800, 200, .4), .003, 1.2), .6),
                                  gain(env(lowpass(osc("saw", 900, 90, .4), 5000, 300), .003, 1.2), .45)), .12, .3, .35, .4)
S["scrape_on"] = lambda: echo(mix(gain(swell(trem(lowpass(noise(.7), 900, 2600), 17, .7), .6), .7),
                                  gain(swell(lowpass(osc("saw", 80, 140, .7), 900), .6), .5), (bell(1500, .3, .2), .45)), .12, .3, .35, .4)
S["scrape_off"] = lambda: echo(mix(gain(env(trem(lowpass(noise(.5), 2600, 500), 17, .7), .005, 1.5), .6),
                                   gain(env(lowpass(osc("saw", 140, 60, .5), 900), .005, 1.5), .5)), .12, .3, .35, .4)
S["module"] = lambda: echo(mix(hiss(.3, 6000, 2500, .45), (bell(1320, .45, .45), .12), (bell(1980, .45, .35), .2)), .13, .38, .45, .5)
S["jettison"] = lambda: echo(mix(thud(50, .4, 1), relay(.7), (hiss(.8, 7000, 900, .6), .05)), .15, .35, .4, .6)

# --- social / seat ---
S["accept"] = lambda: echo(mix(bell(659, .5, .55), (bell(988, .6, .55), .11), (bell(1319, .7, .4), .22)), .14, .38, .45, .6)
S["decline"] = lambda: echo(mix(lowpass(env(osc("square", 494, 494, .12), .003, 2), 1800), (lowpass(env(osc("square", 370, 370, .18), .003, 2), 1800), .13)), .12, .3, .35, .4)
S["chat"] = lambda: echo(mix(gain(env(lowpass(noise(.03), 4000), .001, 2), .3), (chirp(1500, 2200, .05, g=.6), .02)), .1, .3, .35, .3)
S["headtrack_on"] = lambda: echo(mix(blip(1000, .04, "triangle", .6), (blip(1500, .06, "triangle", .6), .05)), .1, .3, .35, .3)
S["headtrack_off"] = lambda: echo(mix(blip(1500, .04, "triangle", .6), (blip(1000, .06, "triangle", .6), .05)), .1, .3, .35, .3)
S["recenter"] = lambda: echo(mix(*[(blip(1200, .03, "triangle", .55), .05 * k) for k in range(3)]), .1, .3, .35, .3)
S["exit_seat"] = lambda: echo(mix(relay(.7), (hiss(.6, 6000, 1200, .55), .03), (thud(60, .3, .8), .1),
                                  (gain(swell(lowpass(osc("saw", 140, 70, .5), 600), .1), .35), .1)), .12, .3, .35, .45)


def write(name, sig):
    peak = max(1e-6, max(abs(x) for x in sig))
    rms = math.sqrt(sum(x * x for x in sig) / len(sig))
    g = min(0.85 / peak, 0.16 / max(1e-6, rms))  # even out loudness between sounds
    # trim trailing near-silence
    end = len(sig)
    while end > 1 and abs(sig[end - 1] * g) < 0.002:
        end -= 1
    fade = min(n_of(.01), end)
    data = bytearray()
    for i in range(end):
        x = sig[i] * g * (min(1.0, (end - i) / fade))
        data += struct.pack("<h", int(max(-1, min(1, x)) * 32767))
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(data))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, make in S.items():
        TS = 1.0
        sig = make()
        if len(sig) / SR > MAX_LEN:
            TS = MAX_LEN / (len(sig) / SR)
            sig = make()
        write(name, sig)
    print(f"wrote {len(S)} sounds to {OUT}")
