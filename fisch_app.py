#!/usr/bin/env python3
"""Fisch Makro - app med sidopanel. Ubuntu (Wayland) + Sober.

Fiskar själv: kastar, klickar på SHAKE-knapparna, håller baren över fisken
(även när fisken är utanför baren) och känner igen fångst via progressbaren.

Starta:  python3 fisch_app.py   (eller via ikonen i appmenyn)
  F6  - starta / stoppa
  F8  - spara skärmbild
  Esc - stoppa
"""
import json
import os
import queue
import random
import shutil
import struct
import subprocess
import sys
import threading
import time
import zlib

VERSION = "2.4"   # höj vid varje ny version så att man ser vilken man kör
UPPDATERA_URL = "https://raw.githubusercontent.com/quranzy2011-byte/cluade/main/fisch_app.py"
GITHUB_API = "https://api.github.com"
DIAG_REPO = "quranzy2011-byte/cluade-2"   # privat repo dit diagnostiken laddas upp
DIAG_GREN = "diagnostik"

MAPP = os.path.dirname(os.path.abspath(__file__))
KONFIG = os.path.expanduser("~/.config/fisch-makro/installningar.json")
STAT_FIL = os.path.expanduser("~/.config/fisch-makro/statistik.json")

STANDARD = {
    "cast_tid": 1.0,        # sekunder att hålla inne för kast (om kastmätaren inte syns)
    "perfekt_kast": True,   # följ kastmätaren och släpp när den når den gröna toppen
    "förutsägelse": 0.14,   # sekunder framåt som fiskens rörelse förutsägs
    "mörk_max": 4.0,        # max sekunder med fisken utanför baren innan den räknas som tappad
    "napp_timeout": 30.0,   # kasta om ifall inget napp
    "shake": "navigation",  # "navigation" (UI Navigation + Enter), "klick" (hittar knappen) eller "av"
    "nav_kod": 43,          # tangentkoden för UI Navigation i Roblox (43 = \\-tangenten)
    "slumpa": True,         # små slumpade variationer i tider och klick
    "notiser": True,        # notis + ljud när makrot stoppar
    "anti_afk": True,       # rör musen lite då och då när makrot är pausat (inget idle-kick)
    "diagnostik": True,     # spara bilder + rapport i autoclicker/diagnostik (för förbättringar)
    "gh_token": "",         # GitHub-token: laddar upp diagnostiken automatiskt (tomt = av)
    "discord": "",          # Discord-webhook för notiser (tomt = av)
    "stopp_fiskar": 0,      # stoppa efter så många fångade fiskar (0 = aldrig)
    "stopp_minuter": 0,     # stoppa efter så många minuter (0 = aldrig)
    "överst": True,         # fönstret alltid överst
}
REEL_OMRÅDE = (0.20, 0.60, 0.80, 0.97)   # x0, y0, x1, y1 som andel av skärmen
SHAKE_OMRÅDE = (0.08, 0.08, 0.92, 0.80)  # där shake-knapparna kan dyka upp

KEY_ENTER, BTN_LEFT = 28, 272

PAKET = ["python3-evdev", "python3-numpy", "python3-gi", "python3-tk", "gir1.2-gstreamer-1.0",
         "gir1.2-gst-plugins-base-1.0", "gstreamer1.0-pipewire"]

# Körs som root: styr musen/tangentbordet och läser F6/F8/Esc.
# "fisch-makro" är en vanlig mus (knappar), "fisch-makro-pekare" en absolut
# pekare som kan flytta muspekaren till en exakt punkt (för shake-klick).
HJÄLPARE = r'''
import os, select, sys
import evdev
from evdev import UInput, AbsInfo, ecodes as e
os.system("modprobe uinput 2>/dev/null")
kbs = [evdev.InputDevice(p) for p in evdev.list_devices()]
kbs = [d for d in kbs if e.KEY_F6 in d.capabilities().get(e.EV_KEY, [])]
if not kbs:
    print("FEL Hittade inget tangentbord", flush=True); sys.exit(1)
ui = UInput({e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT] + list(range(1, 249)),
             e.EV_REL: [e.REL_X, e.REL_Y]}, name="fisch-makro")
MAX = 32767
pek = UInput({e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
              e.EV_ABS: [(e.ABS_X, AbsInfo(0, 0, MAX, 0, 0, 0)),
                         (e.ABS_Y, AbsInfo(0, 0, MAX, 0, 0, 0))]},
             name="fisch-makro-pekare")
names = {e.KEY_F6: "F6", e.KEY_F8: "F8", e.KEY_ESC: "ESC"}
print("OK", flush=True)
buf = b""
lär = False
nere = set()
try:
    while True:
        ready, _, _ = select.select(kbs + [0], [], [])
        for d in ready:
            if d == 0:
                data = os.read(0, 4096)
                if not data:
                    raise SystemExit
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    del_ = line.decode().split()
                    if del_[0] == "lär":
                        lär = True
                    elif del_[0] == "rör":
                        ui.write(e.EV_REL, e.REL_X, int(del_[1]))
                        ui.write(e.EV_REL, e.REL_Y, int(del_[2]))
                        ui.syn()
                    elif del_[0] == "flytta":
                        fx, fy = float(del_[1]), float(del_[2])
                        pek.write(e.EV_ABS, e.ABS_X, int(min(max(fx, 0), 1) * MAX))
                        pek.write(e.EV_ABS, e.ABS_Y, int(min(max(fy, 0), 1) * MAX))
                        pek.syn()
                    else:
                        kod = int(del_[1])
                        if del_[0] == "ner":
                            nere.add(kod)
                        else:
                            nere.discard(kod)
                        ui.write(e.EV_KEY, kod, 1 if del_[0] == "ner" else 0); ui.syn()
            else:
                for ev in d.read():
                    if ev.type != e.EV_KEY or ev.value != 1:
                        continue
                    if lär:
                        lär = False
                        print(f"TANGENT {ev.code}", flush=True)
                    elif ev.code in names:
                        print(names[ev.code], flush=True)
finally:
    for c in nere | {e.BTN_LEFT}:
        ui.write(e.EV_KEY, c, 0)
    ui.syn(); ui.close(); pek.close()
'''


def root_kommando(args):
    """pkexec ger en grafisk lösenordsruta; sudo används om pkexec saknas."""
    grafisk = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if grafisk and shutil.which("pkexec"):
        return ["pkexec"] + args
    return ["sudo"] + args


class Input:
    """Skickar tryck till root-hjälparen och tar emot snabbtangenter."""

    def __init__(self, on_key):
        self.p = subprocess.Popen(root_kommando(["/usr/bin/python3", "-c", HJÄLPARE]),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        first = self.p.stdout.readline().strip()
        if first != "OK":
            raise RuntimeError(first or "Fick inte behörighet (fel lösenord eller avbrutet?)")
        self.held = set()
        self.lock = threading.Lock()
        threading.Thread(target=self._read, args=(on_key,), daemon=True).start()

    def _read(self, on_key):
        for line in self.p.stdout:
            on_key(line.strip())

    def _send(self, text):
        with self.lock:
            self.p.stdin.write(text + "\n")
            self.p.stdin.flush()

    def down(self, code):
        if code not in self.held:
            self.held.add(code)
            self._send(f"ner {code}")

    def up(self, code):
        if code in self.held:
            self.held.discard(code)
            self._send(f"upp {code}")

    def tap(self, *codes):
        for c in codes:
            self._send(f"ner {c}")
        time.sleep(0.03)
        for c in reversed(codes):
            self._send(f"upp {c}")

    def rör(self, dx, dy):
        """Flytta muspekaren relativt (dx, dy) pixlar."""
        self._send(f"rör {int(dx)} {int(dy)}")

    def lär(self):
        """Nästa tangent du trycker rapporteras som 'TANGENT <kod>'."""
        self._send("lär")

    def flytta(self, fx, fy):
        """Flytta muspekaren till (fx, fy) som andel av skärmen (0-1)."""
        self._send(f"flytta {fx:.5f} {fy:.5f}")

    def release_all(self):
        for c in list(self.held):
            self.up(c)

    def stäng(self):
        try:
            self.release_all()
            self.p.stdin.close()
        except (OSError, ValueError):
            pass


class Skärm:
    """Skärminspelning via xdg-desktop-portal + PipeWire (fungerar på Wayland)."""

    TOKEN_FIL = os.path.expanduser("~/.config/fisch-makro/token")

    def __init__(self):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gio, GLib, Gst
        self.Gio, self.GLib, self.Gst = Gio, GLib, Gst
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")
        self.n = 0
        V = GLib.Variant

        res = self._request("CreateSession", lambda t: V("(a{sv})", ({
            "handle_token": V("s", t), "session_handle_token": V("s", "fisch")},)))
        session = res["session_handle"]

        opts = {"types": V("u", 1), "multiple": V("b", False), "persist_mode": V("u", 2)}
        try:
            with open(self.TOKEN_FIL) as f:
                opts["restore_token"] = V("s", f.read().strip())
        except OSError:
            pass
        self._request("SelectSources", lambda t: V("(oa{sv})", (
            session, dict(opts, handle_token=V("s", t)))))
        res = self._request("Start", lambda t: V("(osa{sv})", (
            session, "", {"handle_token": V("s", t)})))
        if res.get("restore_token"):
            os.makedirs(os.path.dirname(self.TOKEN_FIL), exist_ok=True)
            with open(self.TOKEN_FIL, "w") as f:
                f.write(res["restore_token"])
        node = res["streams"][0][0]

        result, fds = self.bus.call_with_unix_fd_list_sync(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.ScreenCast", "OpenPipeWireRemote",
            V("(oa{sv})", (session, {})), GLib.VariantType("(h)"),
            Gio.DBusCallFlags.NONE, -1, None, None)
        fd = fds.get(result.unpack()[0])

        Gst.init(None)
        self.pipeline = Gst.parse_launch(
            f"pipewiresrc fd={fd} path={node} always-copy=true do-timestamp=true ! "
            "videoconvert ! video/x-raw,format=BGRx ! "
            "appsink name=sink max-buffers=1 drop=true sync=false")
        self.sink = self.pipeline.get_by_name("sink")
        self.pipeline.set_state(Gst.State.PLAYING)
        self.bild = None
        self.antal = 0          # antal mottagna bilder
        self.tider = []         # tidpunkter för de senaste bilderna (för bilder/s)

    def _request(self, method, params):
        self.n += 1
        token = f"fisch{os.getpid()}_{self.n}"
        path = f"/org/freedesktop/portal/desktop/request/{self.sender}/{token}"
        svar = {}
        ctx = self.GLib.MainContext.new()
        ctx.push_thread_default()
        try:
            loop = self.GLib.MainLoop.new(ctx, False)

            def cb(_c, _s, _o, _i, _sig, params_):
                svar["code"], svar["res"] = params_.unpack()
                loop.quit()

            sub = self.bus.signal_subscribe(
                "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
                path, None, self.Gio.DBusSignalFlags.NONE, cb)
            self.bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                               "org.freedesktop.portal.ScreenCast", method, params(token),
                               None, self.Gio.DBusCallFlags.NONE, -1, None)
            loop.run()
            self.bus.signal_unsubscribe(sub)
        finally:
            ctx.pop_thread_default()
        if svar["code"] != 0:
            raise RuntimeError("Skärmdelningen avbröts.")
        return svar["res"]

    def bilder_per_s(self):
        nu = time.time()
        return len([t for t in self.tider if nu - t < 2]) / 2

    def hämta(self):
        """Senaste bilden som numpy-array (höjd, bredd, 3) i BGR."""
        import numpy as np
        sample = self.sink.emit("try-pull-sample", 50 * self.Gst.MSECOND)
        if sample is None:
            return self.bild
        s = sample.get_caps().get_structure(0)
        w, h = s.get_value("width"), s.get_value("height")
        buf = sample.get_buffer()
        ok, info = buf.map(self.Gst.MapFlags.READ)
        if not ok:
            return self.bild
        try:
            data = np.frombuffer(info.data, np.uint8)
            stride = len(data) // h
            self.bild = data[: stride * h].reshape(h, stride // 4, 4)[:, :w, :3].copy()
            self.antal += 1
            nu = time.time()
            self.tider = [t for t in self.tider[-60:] if nu - t < 2] + [nu]
        finally:
            buf.unmap(info)
        return self.bild


# ---------------------------------------------------------------- Bildanalys

def _lo_hi(a):
    """Minsta och största färgkanal per pixel (snabbare än a.min(axis=2))."""
    import numpy as np
    b, g, r = a[..., 0], a[..., 1], a[..., 2]
    return np.minimum(np.minimum(b, g), r), np.maximum(np.maximum(b, g), r)


def _körningar(xs, glapp):
    """Delar upp sorterade index i sammanhängande bitar (tillåter små glapp)."""
    import numpy as np
    if len(xs) == 0:
        return []
    return np.split(xs, np.flatnonzero(np.diff(xs) > glapp) + 1)


def hitta_reel(bild, rader=None):
    """Letar upp den ljusa spelarbaren (fisken inne i baren).

    Returnerar (bar_x0, bar_x1, fisk_x, rad0, rad1) i skärmkoordinater, annars None.
    fisk_x är None om fisken inte syns. Fisken är det mörka lodräta strecket
    som går genom hela barens höjd; pilarna täcker bara en del och räknas inte.
    """
    import numpy as np
    H, W = bild.shape[:2]
    x0, y0, x1, y1 = (int(REEL_OMRÅDE[0] * W), int(REEL_OMRÅDE[1] * H),
                      int(REEL_OMRÅDE[2] * W), int(REEL_OMRÅDE[3] * H))
    if rader:  # snabbspår: bara raderna runt där baren låg förra gången
        y0, y1 = max(y0, rader[0]), min(y1, rader[1])
    reg = bild[y0:y1, x0:x1]
    rw = reg.shape[1]

    lo, hi = _lo_hi(reg)
    ljus = (lo >= 170) & (hi - lo <= 45)
    rader = np.flatnonzero(ljus.sum(axis=1) >= max(8, rw * 0.05))
    if len(rader) == 0:
        return None
    band = max(_körningar(rader, 2), key=len)
    if len(band) < max(6, H * 0.012):
        return None
    ra, rb = band[0], band[-1] + 1

    andel = ljus[ra:rb].mean(axis=0)
    xs = np.flatnonzero(andel >= 0.3)
    if len(xs) == 0:
        return None
    del_ = max(_körningar(xs, rw * 0.03), key=lambda d: d[-1] - d[0])
    b0, b1 = int(del_[0]), int(del_[-1])
    if not (rw * 0.05 <= b1 - b0 <= rw * 0.8):
        return None

    fisk = None
    inre = andel[b0 + 2:b1 - 1]
    mörk = np.flatnonzero(inre < 0.25)
    if len(mörk):
        bäst = min(_körningar(mörk, 2), key=lambda k: inre[k].mean())
        fisk = int(bäst.mean()) + b0 + 2 + x0
    return (b0 + x0, b1 + x0, fisk, ra + y0, rb + y0)


def hitta_streck(remsa, W):
    """Hittar smala lodräta streck som går genom nästan hela remsans höjd.

    Ett streck skiljer sig från BÅDA sidorna (en kant bara från en sida),
    och pilar/text täcker bara en del av höjden. Returnerar [(x, styrka)].
    """
    import numpy as np
    s = remsa.astype(np.int32)
    rows, cols = s.shape[:2]
    g, sp = max(4, W // 300), 5
    if cols < 2 * (g + sp) + 2 or rows < 3:
        return []
    cs = np.concatenate([np.zeros((rows, 1, 3), np.int32), np.cumsum(s, axis=1)], axis=1)
    xs = np.arange(g + sp - 1, cols - g - sp + 1)
    vä = (cs[:, xs - g + 1] - cs[:, xs - g - sp + 1]) / sp
    hö = (cs[:, xs + g + sp] - cs[:, xs + g]) / sp
    mitt = s[:, xs]
    dv = np.abs(mitt - vä).max(axis=2)
    dh = np.abs(mitt - hö).max(axis=2)
    täckning = np.minimum((dv > 25).mean(axis=0), (dh > 25).mean(axis=0))
    styrka = np.minimum(np.median(dv, axis=0), np.median(dh, axis=0))
    kand = np.flatnonzero(täckning >= 0.6)
    ut = []
    for k in _körningar(kand, 1):
        if len(k) > 2 * g + 1:
            continue
        ut.append((int(xs[k].mean()), float(styrka[k].mean())))
    return ut


def läs_progress(bild, rb, bandhöjd, x0, x1):
    """Hur full progressbaren under spåret är (0-1), eller None om den inte syns.

    Progressbaren har en vit ram; ramens längd = full bar, den vita
    fyllningen från vänster = hur långt fångsten har kommit."""
    import numpy as np
    H = bild.shape[0]
    ya, yb = min(H, rb + max(2, int(bandhöjd * 0.2))), min(H, rb + int(bandhöjd * 3))
    if yb - ya < 2:
        return None
    lo = _lo_hi(bild[ya:yb, x0:x1])[0]
    # Ramens övre/nedre kant: rader där ljusa pixlar täcker det mesta av bredden.
    kanter = []
    for i, rad in enumerate(lo):
        xs = np.flatnonzero(rad >= 100)
        if len(xs) > 10 and len(xs) >= 0.5 * (xs[-1] - xs[0]):
            kanter.append((i, xs[0], xs[-1]))
    # Ramen = två kanter (övre och nedre) med samma vänster- och högerände.
    ram = None
    for i, (ya_, va, ha) in enumerate(kanter):
        for yb_, vb, hb in kanter[i + 1:]:
            if 3 <= yb_ - ya_ <= 30 and abs(va - vb) <= 4 and abs(ha - hb) <= 4:
                if ram is None or ha - va > ram[3] - ram[2]:
                    ram = (ya_, yb_, min(va, vb), max(ha, hb))
    if ram is None:
        return None
    topp, botten, vä, hö = ram
    total = hö - vä
    if total < max(40, bandhöjd * 2, bild.shape[1] * 0.1):
        return None
    # Riktig ram: vita sidokanter på raderna mellan övre och nedre kanten.
    inne = lo[topp + 1:botten]
    sidor = ((inne[:, max(0, vä - 1):vä + 2] >= 100).any(axis=1).mean(),
             (inne[:, max(0, hö - 1):hö + 2] >= 100).any(axis=1).mean())
    if min(sidor) < 0.7:
        return None
    # Fyllningen: ljus körning från vänsterkanten, på raderna innanför ramen.
    fyllning = []
    for rad in lo[topp + 1:botten]:
        xs = np.flatnonzero(rad[vä:hö + 1] >= 140)
        n = 0
        if len(xs) and xs[0] <= 3:
            # tillåt små avbrott (t.ex. fiskelinan som korsar fyllningen)
            n = int(_körningar(xs, 8)[0][-1])
            if n >= total - 3 and len(xs) < 0.9 * total:
                n = 0   # bara ramens högerkant, ingen fyllning
        fyllning.append(n)
    return min(1.0, float(np.median(fyllning)) / total)


def hitta_kastmätare(bild):
    """Hittar kastmätaren: en smal lodrät stapel bredvid gubben som fylls med
    vitt nerifrån, med en grön topp. Returnerar (andel 0-1, x) eller None."""
    import numpy as np
    H, W = bild.shape[:2]
    x0, x1, y0, y1 = int(0.35 * W), int(0.75 * W), int(0.25 * H), int(0.85 * H)
    reg = bild[y0:y1, x0:x1]
    lo, hi = _lo_hi(reg)
    vit = (lo >= 200) & (hi - lo <= 40)
    kol = np.flatnonzero(vit.sum(axis=0) >= 0.03 * H)
    bäst = None
    for g in _körningar(kol, 1):
        if not (3 <= len(g) <= 16):
            continue
        rader = np.flatnonzero(vit[:, g].mean(axis=1) >= 0.6)
        if len(rader) == 0:
            continue
        run = max(_körningar(rader, 2), key=len)
        topp, botten = int(run[0]), int(run[-1])
        if botten - topp < 0.03 * H:
            continue
        # Ovanför fyllningen: mörkt spår och sedan en grön topp.
        b, gr, r = (reg[:, g, i].astype(int).mean(axis=1) for i in range(3))
        grön = (gr > 100) & (gr > r + 35) & (gr > b + 20)
        mörk = np.maximum(np.maximum(b, gr), r) < 70
        lock = None
        y = topp - 1
        while y >= max(0, topp - int(0.4 * H)):
            if grön[y]:
                lock = y
                break
            if not mörk[y] and topp - y > 3:
                break
            y -= 1
        if lock is None:
            continue
        # Mätarens totala höjd: från under den gröna toppen till botten.
        full = botten - lock
        if full < 0.05 * H:
            continue
        andel = (botten - topp) / full
        if bäst is None or full > bäst[1]:
            bäst = (min(1.0, andel), full, x0 + int(g.mean()))
    return (bäst[0], bäst[2]) if bäst else None


def spårmask(remsa, gräns=60):
    """Andel 'spårmörka' pixlar per kolumn (spåret är mörkt; gränsen lärs in)."""
    import numpy as np
    h = remsa.shape[0]
    inre = remsa[h // 6: h - h // 6] if h > 8 else remsa
    return (_lo_hi(inre)[1] < gräns).mean(axis=0)


def lär_spårgräns(remsa, b0, b1):
    """Spårets ljushet bredvid den vita baren -> gräns för vad som räknas som spår."""
    import numpy as np
    h = remsa.shape[0]
    inre = remsa[h // 6: h - h // 6] if h > 8 else remsa
    hi = _lo_hi(inre)[1]
    sidor = [hi[:, max(0, b0 - 40):max(0, b0 - 8)], hi[:, b1 + 8:b1 + 40]]
    värden = np.concatenate([x.ravel() for x in sidor if x.size])
    if värden.size < 20:
        return None
    return float(min(140, max(60, np.percentile(värden, 75) + 30)))


def hitta_spann(remsa, b0, b1, gräns=60):
    """Spårets utsträckning: mörka kolumner på båda sidor om baren (b0-b1)."""
    import numpy as np
    mörk = spårmask(remsa, gräns) >= 0.8
    n = len(mörk)

    def gå(x, steg):
        glapp = 0
        while 0 <= x + steg < n:
            if mörk[x + steg] or glapp < 6:
                glapp = 0 if mörk[x + steg] else glapp + 1
                x += steg
            else:
                break
        return x
    return gå(max(0, b0 - 1), -1), gå(min(n - 1, b1 + 1), 1)


def hitta_ute_bar(remsa, bredd, förra_mitt, spann, fisk_x=None, gräns=60):
    """Hittar baren när fisken är utanför och baren blivit genomskinlig.

    Spåret är nästan svart; baren är det breda stycket på spåret som inte är
    svart (vilken färg som helst, även med bakgrunden synlig igenom)."""
    import numpy as np
    mörk = spårmask(remsa, gräns)
    a, b = spann if spann else (0, len(mörk) - 1)
    ej_mörk = mörk < 0.5
    ej_mörk[:max(0, a)] = False
    ej_mörk[b + 1:] = False
    for fx in fisk_x or []:                     # fiskmarkören/streck är inte baren
        ej_mörk[max(0, fx - 6):fx + 7] = False
    bäst = None
    for k in _körningar(np.flatnonzero(ej_mörk), max(3, int(bredd * 0.06))):
        w = k[-1] - k[0]
        kant = k[0] <= a + 3 or k[-1] >= b - 3   # baren kan klippas mot spårets kant
        if not ((0.6 if not kant else 0.3) * bredd <= w <= 1.25 * bredd):
            continue
        mitt = (k[0] + k[-1]) / 2
        flytt = abs(mitt - förra_mitt) if förra_mitt is not None else 0
        if flytt > len(mörk) * 0.3:
            continue
        fel = abs(w - bredd) * (0.3 if kant else 1) + 0.5 * flytt
        if bäst is None or fel < bäst[0]:
            bäst = (fel, int(k[0]), int(k[-1]))
    return (bäst[1], bäst[2]) if bäst else None


class Syn:
    """Följer reel-minispelet mellan bilderna, även när baren blir mörk."""

    def __init__(self):
        self.band = None        # (rad0, rad1) där baren ligger
        self.bar_bredd = None   # barens bredd i px (lärs in)
        self.aktiv = False
        self.spann = None       # spårets utsträckning (x0, x1) i remsan
        self.gräns = None       # hur ljust spåret får vara (lärs in)
        self.fisk = None        # senaste fisk-x
        self.bar_mitt = None    # senaste barens mitt
        self.full_prog = 0      # längsta progress som setts (= full bar)

    def ny_reel(self):
        self.spann = None
        self.aktiv = False
        self.linor = None
        self.fisk = None

    def läs(self, bild):
        """Returnerar (läge, bar0, bar1, fisk, progress). läge = 'vit', 'mörk' eller None."""
        import numpy as np
        H, W = bild.shape[:2]
        x0, x1 = int(REEL_OMRÅDE[0] * W), int(REEL_OMRÅDE[2] * W)
        self.n = getattr(self, "n", 0) + 1
        r = None
        if self.band:
            ra, rb = self.band
            r = hitta_reel(bild, (ra - (rb - ra), rb + (rb - ra)))
        # Hela sökningen är långsam; under en pågående reel räcker det ibland.
        if r is None and (not self.aktiv or self.n % 6 == 0):
            r = hitta_reel(bild)
        if r:
            b0, b1, fisk, ra, rb = r
            self.band = (ra, rb)
            bredd = b1 - b0
            if self.bar_bredd is None or abs(bredd - self.bar_bredd) < self.bar_bredd * 0.3:
                self.bar_bredd = bredd if self.bar_bredd is None else \
                    0.8 * self.bar_bredd + 0.2 * bredd
            self.aktiv = True
            self.bar_mitt = (b0 + b1) / 2
            if self.n % 5 == 1 or self.spann is None:
                remsa = bild[ra:rb, x0:x1]
                g = lär_spårgräns(remsa, b0 - x0, b1 - x0)
                if g is not None:
                    self.gräns = g if self.gräns is None else 0.7 * self.gräns + 0.3 * g
                self.spann = hitta_spann(remsa, b0 - x0, b1 - x0, self.gräns or 60)
            if fisk is not None:
                self.fisk = fisk
            prog = läs_progress(bild, rb, rb - ra, x0, x1)
            return ("vit", b0, b1, fisk, prog)

        if not (self.aktiv and self.band):
            return (None, None, None, None, None)

        # Baren är mörk (fisken utanför). Leta efter fisk-strecket och den mörka baren.
        ra, rb = self.band
        remsa = bild[ra:rb, x0:x1]
        streck = hitta_streck(remsa, W)
        bh = rb - ra
        ovan = bild[max(0, ra - int(bh * 2.5)):max(0, ra - int(bh * 1.2)), x0:x1]
        if len(ovan) >= 3 and streck:
            if self.n % 10 == 0 or getattr(self, "linor", None) is None:
                self.linor = [x for x, _ in hitta_streck(ovan, W)]
            linor = self.linor
            streck = [st for st in streck if all(abs(st[0] - x) > 4 for x in linor)]
        # 1) Baren först (alla streck maskas bort så att fisken inte räknas som bar).
        b0 = b1 = None
        if self.bar_bredd:
            bar = hitta_ute_bar(remsa, self.bar_bredd,
                                None if self.bar_mitt is None else self.bar_mitt - x0,
                                self.spann, [x for x, _ in streck], self.gräns or 60)
            if bar:
                b0, b1 = bar[0] + x0, bar[1] + x0
                self.bar_mitt = (b0 + b1) / 2
                # 2) Fisken är utanför baren: släng streck inne i baren och på kanterna.
                streck = [st for st in streck if not (b0 - 4 <= st[0] + x0 <= b1 + 4)]

        # 3) Fisken: närmast där den sågs senast (den rör sig inte i språng).
        fisk = None
        if streck:
            if self.fisk is not None:
                nära = [s for s in streck if abs(s[0] + x0 - self.fisk) < (x1 - x0) * 0.25]
                if nära:
                    fisk = min(nära, key=lambda s: abs(s[0] + x0 - self.fisk))[0] + x0
            else:
                fisk = max(streck, key=lambda s: s[1])[0] + x0

        # Finns minispelet kvar? Spåret (utom baren) ska vara mörkt, eller
        # progressbarens ram synas. Annars har det försvunnit (fångad/tappad).
        prog = läs_progress(bild, rb, rb - ra, x0, x1)
        if self.spann:
            a, b = self.spann
            mörk = spårmask(remsa, self.gräns or 60)[a:b + 1]
            if b0 is not None:
                mörk = np.concatenate([mörk[:max(0, b0 - x0 - a)], mörk[b1 - x0 - a + 1:]])
            andel = mörk.mean() if len(mörk) >= 10 else 0.0
            if andel < 0.5 and prog is None:
                return (None, None, None, None, None)
        elif prog is None:
            return (None, None, None, None, None)
        if fisk is None and b0 is None:
            return (None, None, None, None, None)
        if fisk is not None:
            self.fisk = fisk
        return ("mörk", b0, b1, fisk, prog)


_RINGAR = {}


def _ringkärna(r, form):
    """FFT av en ringmall med radie r: + på en tunn ring, - inuti (ovanför och
    under texten) och strax utanför. En ifylld vit fläck ger därför låg poäng."""
    import numpy as np
    nyckel = (r, form)
    if nyckel not in _RINGAR:
        t = max(1.0, r * 0.05)
        k = int(np.ceil(r + 2 * t + 2))
        yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
        d = np.sqrt(yy ** 2 + xx ** 2)
        ring = (d >= r - t) & (d <= r + t)
        disk = (d <= 0.65 * r) & (np.abs(yy) >= 0.3 * r)
        ute = (d >= r + t + 1) & (d <= r + 2 * t + 2)
        kärna = ring / ring.sum() - disk / max(1, disk.sum()) - 0.5 * ute / ute.sum()
        if len(_RINGAR) > 200:
            _RINGAR.clear()
        _RINGAR[nyckel] = (np.fft.rfft2(kärna, form), k)
    return _RINGAR[nyckel]


def _ringar(mask, radier):
    """Bästa ringen för varje radie: lista med (poäng, y, x, r)."""
    import numpy as np
    h, w = mask.shape
    kmax = int(np.ceil(max(radier) * 1.1 + 4))
    form = (h + 2 * kmax + 1, w + 2 * kmax + 1)
    F = np.fft.rfft2(mask, form)
    ut = []
    for r in radier:
        r = round(float(r), 2)
        K, k = _ringkärna(r, form)
        poäng = np.fft.irfft2(F * K, form)[k:k + h, k:k + w]
        cy, cx = np.unravel_index(np.argmax(poäng), poäng.shape)
        ut.append((float(poäng[cy, cx]), int(cy), int(cx), r))
    return ut


def _ringtäckning(vit, cy, cx, R):
    """Hur stor del av varvet (72 vinklar) som har vitt nära radien R."""
    import numpy as np
    v = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    träff = np.zeros(72, bool)
    h, w = vit.shape
    for f in np.linspace(0.82, 1.12, max(6, int(R * 0.3) + 1)):
        yy = np.round(cy + R * f * np.sin(v)).astype(int)
        xx = np.round(cx + R * f * np.cos(v)).astype(int)
        inne = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < w)
        träff[inne] |= vit[yy[inne], xx[inne]]
    return träff.mean()


def hitta_shake(bild):
    """Letar efter en SHAKE-knapp: vit ring med mörk insida och vit text.

    1. Grovsökning med en ringmall i låg upplösning (FFT) i flera storlekar.
    2. De bästa kandidaterna finjusteras i full upplösning.
    3. Kontroll: ringen ska gå runt nästan hela varvet och insidan vara mörk.
    Returnerar (x, y) i skärmkoordinater eller None.
    """
    import numpy as np
    H, W = bild.shape[:2]
    s = 4
    x0, y0 = int(SHAKE_OMRÅDE[0] * W), int(SHAKE_OMRÅDE[1] * H)
    x1, y1 = int(SHAKE_OMRÅDE[2] * W), int(SHAKE_OMRÅDE[3] * H)
    h, w = (y1 - y0) // s, (x1 - x0) // s
    reg = bild[y0:y0 + h * s, x0:x0 + w * s]

    def vitmask(a):
        lo, hi = _lo_hi(a)
        return (lo >= 155) & (hi - lo <= 40)

    # Varannan pixel, max per 2x2 och lite förtjockning: även tunna ringar syns.
    vit = vitmask(reg[::2, ::2]).reshape(h, 2, w, 2).max(axis=(1, 3))
    tjock = vit.copy()
    tjock[1:] |= vit[:-1]
    tjock[:-1] |= vit[1:]
    vit = tjock.copy()
    vit[:, 1:] |= tjock[:, :-1]
    vit[:, :-1] |= tjock[:, 1:]

    minsta = min(H, W) / s
    kand = sorted(_ringar(vit.astype(float), np.geomspace(0.022 * minsta, 0.14 * minsta, 13)),
                  reverse=True)
    valda = []
    for k in kand:
        if k[0] < 0.3:
            break
        if all(abs(k[1] - v[1]) > 3 or abs(k[2] - v[2]) > 3 for v in valda):
            valda.append(k)
        if len(valda) == 3:
            break

    bäst = None
    for _, cy, cx, r in valda:
        R = r * s
        m = int(R * 1.4) + 8
        ya, yb = max(0, cy * s - m), min(reg.shape[0], cy * s + m)
        xa, xb = max(0, cx * s - m), min(reg.shape[1], cx * s + m)
        fönster = reg[ya:yb, xa:xb]
        fvit = vitmask(fönster)
        p, fy, fx, R = max(_ringar(fvit.astype(float), np.linspace(R * 0.82, R * 1.18, 7)))
        täck = _ringtäckning(fvit, fy, fx, R)
        mörk = _lo_hi(fönster)[1] < 115
        yy, xx = np.ogrid[:mörk.shape[0], :mörk.shape[1]]
        inne = ((yy - fy) ** 2 + (xx - fx) ** 2 <= (0.65 * R) ** 2) & (np.abs(yy - fy) >= 0.3 * R)
        if täck < 0.8 or not inne.any() or mörk[inne].mean() < 0.5:
            continue
        if bäst is None or täck + p > bäst[0]:
            bäst = (täck + p, x0 + xa + fx, y0 + ya + fy)
    return (bäst[1], bäst[2]) if bäst else None


def spara_png(sökväg, bgr):
    import numpy as np
    h, w = bgr.shape[:2]
    rgb = np.ascontiguousarray(bgr[:, :, ::-1]).reshape(h, w * 3)
    rå = np.concatenate([np.zeros((h, 1), np.uint8), rgb], axis=1).tobytes()

    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    with open(sökväg, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(rå, 6)))
        f.write(chunk(b"IEND", b""))


def tangentnamn(kod):
    """Läsbart namn på en tangentkod (fysisk tangent, oberoende av layout)."""
    kända = {43: "' eller \\ (vid Enter)", 41: "§ (vänster om 1)", 12: "+", 13: "´",
             26: "Å", 27: "¨", 39: "Ö", 40: "Ä", 86: "< (vid Z)", 28: "Enter"}
    if kod in kända:
        return kända[kod]
    try:
        from evdev import ecodes
        namn = ecodes.KEY.get(kod)
        if isinstance(namn, list):
            namn = namn[0]
        if namn:
            return namn.replace("KEY_", "")
    except ImportError:
        pass
    return f"kod {kod}"


def versionstal(text):
    """'2.1' -> (2, 1) så att versioner kan jämföras."""
    try:
        return tuple(int(d) for d in text.strip().split("."))
    except ValueError:
        return (0,)


def hämta_senaste():
    """Hämtar senaste fisch_app.py. Returnerar (version, källkod)."""
    import re
    import urllib.request
    req = urllib.request.Request(UPPDATERA_URL + f"?t={int(time.time())}",
                                 headers={"User-Agent": "FischMakro", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=15) as svar:
        kod = svar.read().decode("utf-8")
    m = re.search(r'^VERSION = "([0-9.]+)"', kod, re.M)
    if not m:
        raise RuntimeError("hittade inget versionsnummer i den hämtade filen")
    compile(kod, "fisch_app.py", "exec")   # kasta fel om filen är trasig
    return m.group(1), kod


def notis(text):
    """Skrivbordsnotis + ljud (om det finns)."""
    try:
        if shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-a", "Fisch Makro", "Fisch Makro", text])
        ljud = "/usr/share/sounds/freedesktop/stereo/complete.oga"
        if shutil.which("paplay") and os.path.exists(ljud):
            subprocess.Popen(["paplay", ljud])
    except OSError:
        pass


# ---------------------------------------------------------------- Diagnostik

class Diagnostik:
    """Samlar det makrot ser och gör, så att det kan förbättras.

    Sparar i autoclicker/diagnostik/<pass>/:
      rapport.json  - fångade/tappade, kast, hur kamperna gick, fel
      *.png         - bilder när en fisk tappas, vid fångst, inget napp och fel
    Med en GitHub-token laddas allt upp automatiskt till ett privat repo.
    """

    MAX_BILDER = 300

    def __init__(self, inst, logg):
        import collections
        self.inst = inst
        self.logg = logg
        self.pass_id = time.strftime("%Y%m%d_%H%M%S")
        self.mapp = os.path.join(MAPP, "diagnostik", self.pass_id)
        self.rapport = {"version": VERSION, "pass": self.pass_id, "start": time.time(),
                        "resultat": {"fångad": 0, "tappad": 0, "inget napp": 0},
                        "kast": [], "kamper": [], "fel": [], "bilder_per_s": []}
        self.kamp = None
        self.buffert = collections.deque(maxlen=8)   # (tid, bild) sista ~2 s i kampen
        self.skrivkö = queue.Queue()
        self.uppkö = queue.Queue()
        self.uppladdat = 0
        self.senast_uppladdat = None
        self.senast_rapport = 0
        self.n_fångstbilder = 0
        threading.Thread(target=self._skrivare, daemon=True).start()
        threading.Thread(target=self._uppladdare, daemon=True).start()

    # ---- insamling (anropas från makrotråden, måste vara snabbt)
    def på(self):
        return bool(self.inst.get("diagnostik"))

    def kast(self, andel):
        if self.på():
            self.rapport["kast"] = (self.rapport["kast"] + [andel])[-500:]

    def kamp_start(self):
        if self.på():
            self.kamp = {"start": round(time.time(), 1), "bilder": 0, "vit": 0, "mörk": 0,
                         "borta": 0, "fisk_i_bar": 0, "fisk_sedd": 0, "prog_max": 0.0}
            self.buffert.clear()

    def kamp_bild(self, bild, läge, b0, b1, fisk, prog):
        k = self.kamp
        if not (self.på() and k):
            return
        k["bilder"] += 1
        k[läge or "borta"] += 1
        if fisk is not None:
            k["fisk_sedd"] += 1
            if b0 is not None and b0 <= fisk <= b1:
                k["fisk_i_bar"] += 1
        if prog is not None:
            k["prog_max"] = max(k["prog_max"], round(float(prog), 3))
            k["prog_slut"] = round(float(prog), 3)
        nu = time.time()
        if bild is not None and (not self.buffert or nu - self.buffert[-1][0] > 0.25):
            self.buffert.append((nu, bild))

    def kamp_slut(self, resultat, kamptid):
        k, self.kamp = self.kamp, None
        if not (self.på() and k):
            return
        k["resultat"] = resultat
        k["tid"] = round(kamptid, 1)
        self.rapport["kamper"] = (self.rapport["kamper"] + [k])[-500:]
        if resultat == "tappad":
            # Bilderna precis innan fisken tappades visar vad som gick fel.
            for i, (t, b) in enumerate(list(self.buffert)[-4:]):
                self.bild(f"tappad_{time.strftime('%H%M%S')}_{i}", b, beskär=True)

    def resultat(self, resultat):
        if self.på():
            self.rapport["resultat"][resultat] = self.rapport["resultat"].get(resultat, 0) + 1
            self.spara_rapport()

    def fångstbild(self, bild):
        """Bilden strax efter en fångst ("I caught a ...!") - för fångstloggen."""
        if self.på() and bild is not None and self.n_fångstbilder < 40:
            self.n_fångstbilder += 1
            self.bild(f"fangst_{time.strftime('%H%M%S')}", bild, halv=True)

    def inget_napp(self, bild):
        if self.på() and bild is not None:
            self.bild(f"inget_napp_{time.strftime('%H%M%S')}", bild, halv=True)

    def fel(self, text, bild=None):
        if self.på():
            self.rapport["fel"] = (self.rapport["fel"] + [[time.strftime("%H:%M:%S"), text]])[-100:]
            if bild is not None:
                self.bild(f"fel_{time.strftime('%H%M%S')}", bild, halv=True)
            self.spara_rapport(nu=True)

    def bild(self, namn, bild, beskär=False, halv=False):
        if bild is not None:
            self.skrivkö.put(("bild", namn, bild, beskär, halv))

    def spara_rapport(self, nu=False, bps=None):
        if bps is not None:
            self.rapport["bilder_per_s"] = (self.rapport["bilder_per_s"] + [round(bps, 1)])[-200:]
        if nu or time.time() - self.senast_rapport > 30:
            self.senast_rapport = time.time()
            self.skrivkö.put(("rapport",))

    def sammanfattning(self):
        r = self.rapport["resultat"]
        f, t = r.get("fångad", 0), r.get("tappad", 0)
        kamper = [k for k in self.rapport["kamper"] if k.get("fisk_sedd")]
        i_bar = (sum(k["fisk_i_bar"] for k in kamper) / max(1, sum(k["fisk_sedd"] for k in kamper)))
        kast = [k for k in self.rapport["kast"] if isinstance(k, (int, float))]
        return {"fångad": f, "tappad": t, "inget_napp": r.get("inget napp", 0),
                "fångstrat": round(f / (f + t), 3) if f + t else None,
                "fisk_i_baren": round(i_bar, 3) if kamper else None,
                "snitt_kast": round(sum(kast) / len(kast), 3) if kast else None,
                "kamper": len(self.rapport["kamper"]), "fel": len(self.rapport["fel"])}

    # ---- bakgrundstrådar (sparar och laddar upp utan att störa fisket)
    def _skrivare(self):
        while True:
            jobb = self.skrivkö.get()
            try:
                os.makedirs(self.mapp, exist_ok=True)
                if jobb[0] == "rapport":
                    self.rapport["sammanfattning"] = self.sammanfattning()
                    self.rapport["uppdaterad"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    sökväg = os.path.join(self.mapp, "rapport.json")
                    with open(sökväg + ".tmp", "w", encoding="utf-8") as fil:
                        json.dump(self.rapport, fil, indent=1, ensure_ascii=False)
                    os.replace(sökväg + ".tmp", sökväg)
                    self.uppkö.put(sökväg)
                else:
                    _, namn, bild, beskär, halv = jobb
                    H, W = bild.shape[:2]
                    if beskär:   # bara reel-området, i full upplösning
                        bild = bild[int(0.55 * H):int(0.97 * H), int(0.15 * W):int(0.85 * W)]
                    elif halv:
                        bild = bild[::2, ::2]
                    sökväg = os.path.join(self.mapp, namn + ".png")
                    spara_png(sökväg, bild)
                    self.uppkö.put(sökväg)
                    self._städa()
            except Exception as fel:
                self.logg(f"Diagnostik: kunde inte spara ({fel})")

    def _städa(self):
        bas = os.path.join(MAPP, "diagnostik")
        bilder = []
        for rot, _, filer in os.walk(bas):
            bilder += [os.path.join(rot, f) for f in filer if f.endswith(".png")]
        if len(bilder) > self.MAX_BILDER:
            for f in sorted(bilder, key=os.path.getmtime)[:len(bilder) - self.MAX_BILDER]:
                try:
                    os.remove(f)
                except OSError:
                    pass

    def _uppladdare(self):
        väntande = {}
        while True:
            try:
                sökväg = self.uppkö.get(timeout=5)
                väntande[sökväg] = True
            except queue.Empty:
                pass
            token = self.inst.get("gh_token", "").strip()
            if not token or not väntande:
                continue
            # Bilder först i tur och ordning, rapporten sist (den skrivs ofta över).
            sökväg = sorted(väntande, key=lambda p: p.endswith(".json"))[0]
            del väntande[sökväg]
            if not os.path.exists(sökväg):
                continue
            try:
                self._ladda_upp(token, sökväg)
                self.uppladdat += 1
                self.senast_uppladdat = time.strftime("%H:%M")
            except Exception as fel:
                self.logg(f"Diagnostik: uppladdning misslyckades ({fel})")
                time.sleep(30)
            time.sleep(2)

    def _ladda_upp(self, token, sökväg):
        import base64
        import urllib.error
        import urllib.request
        rel = os.path.relpath(sökväg, MAPP).replace(os.sep, "/")
        url = f"{GITHUB_API}/repos/{DIAG_REPO}/contents/{rel}"
        huvud = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "FischMakro"}
        sha = None
        try:   # finns filen redan (rapport.json skrivs över) behövs dess sha
            req = urllib.request.Request(f"{url}?ref={DIAG_GREN}", headers=huvud)
            with urllib.request.urlopen(req, timeout=20) as svar:
                sha = json.loads(svar.read()).get("sha")
        except urllib.error.HTTPError as fel:
            if fel.code != 404:
                raise
        with open(sökväg, "rb") as fil:
            data = {"message": f"diagnostik {rel}", "branch": DIAG_GREN,
                    "content": base64.b64encode(fil.read()).decode()}
        if sha:
            data["sha"] = sha
        req = urllib.request.Request(url, data=json.dumps(data).encode(), method="PUT",
                                     headers=dict(huvud, **{"Content-Type": "application/json"}))
        urllib.request.urlopen(req, timeout=60).close()


# ---------------------------------------------------------------- Makrot

class Makro:
    """Fiskelogiken. Körs i en egen tråd och rapporterar till appen via en kö."""

    def __init__(self, inst, händelser):
        self.inst = inst
        self.q = händelser
        self.kör = threading.Event()
        self.spara = threading.Event()
        self.inp = None
        self.skärm = None
        self.syn = Syn()
        self.vy = None          # (bar0, bar1, fisk, bredd, läge) för live-vyn
        self.pekare_flyttad = False
        self.acc = None         # barens acceleration (px/s²), lärs in under spelet
        self.diag = Diagnostik(inst, self.logg)

    def logg(self, text):
        self.q.put(("logg", text))

    def status(self, text):
        self.q.put(("status", text))

    def slump(self, värde, andel=0.08):
        if not self.inst["slumpa"]:
            return värde
        return värde * random.uniform(1 - andel, 1 + andel)

    def vänta(self, sek):
        slut = time.time() + sek
        while True:
            if not self.kör.is_set():
                raise InterruptedError
            self.debug()
            if time.time() >= slut:
                return
            time.sleep(0.02)

    def debug(self):
        if not self.spara.is_set():
            return
        self.spara.clear()
        try:
            if self.skärm is None:
                self.logg("Skärmbild: skärmdelningen är inte igång (se loggen ovan).")
                return
            bild = self.skärm.hämta()
            if bild is None:
                self.logg(f"Skärmbild: inga bilder från skärmen än "
                          f"({self.skärm.antal} bilder mottagna).")
                return
            namn = time.strftime("fisch_bild_%H%M%S.png")
            sökväg = os.path.join(MAPP, namn)
            spara_png(sökväg, bild)
            self.logg(f"Sparade {sökväg} ({bild.shape[1]}x{bild.shape[0]})")
            self.logg(f"  ser: reel={hitta_reel(bild)} shake={hitta_shake(bild)}")
        except Exception as fel:
            import traceback
            self.logg(f"Skärmbild misslyckades: {fel!r}")
            ram = traceback.extract_tb(fel.__traceback__)[-1]
            self.logg(f"  (rad {ram.lineno} i {ram.name}: {ram.line})")

    def nav(self):
        """Slår på/av UI Navigation i Roblox."""
        self.inp.tap(int(self.inst["nav_kod"]))

    def kasta(self):
        if self.pekare_flyttad:
            # Shake-klicken flyttade pekaren; ställ den mitt i spelet igen.
            self.inp.flytta(self.slump(0.5, 0.02), self.slump(0.45, 0.02))
            self.pekare_flyttad = False
            self.vänta(0.05)
        self.status("Kastar")
        self.inp.down(BTN_LEFT)
        start = time.time()
        if self.inst["perfekt_kast"] and self.skärm is not None:
            if self.perfekt_kast(start):
                return
        self.vänta(max(0.0, self.slump(self.inst["cast_tid"]) - (time.time() - start)))
        self.inp.up(BTN_LEFT)
        self.diag.kast("tid (mätaren syntes inte)" if self.inst["perfekt_kast"] else "tid")

    def perfekt_kast(self, start):
        """Släpper när kastmätaren (förutsagt) når toppen. False = mätaren syntes inte."""
        prover = []
        sett = False
        while True:
            nu = time.time()
            if nu - start > 3.0 or (not sett and nu - start > max(1.2, self.inst["cast_tid"])):
                return sett and self.släpp("maxtid")
            self.vänta(0)
            bild = self.skärm.hämta()
            m = hitta_kastmätare(bild) if bild is not None else None
            if m is None:
                time.sleep(0.005)
                continue
            sett = True
            andel = m[0]
            prover.append((time.time(), andel))
            prover = prover[-5:]
            fart = hastighet(prover)
            # Släpp strax innan toppen (släppet når spelet ~0,05 s senare), eller
            # direkt om mätaren står still/vänder högt upp.
            if andel + max(0.0, fart) * 0.05 >= 0.99 or (andel >= 0.95 and fart <= 0.05):
                return self.släpp(f"{andel:.0%}")
            time.sleep(0.003)

    def släpp(self, orsak):
        self.inp.up(BTN_LEFT)
        self.kast_andel = orsak
        self.diag.kast(float(orsak.rstrip("%")) / 100 if orsak.endswith("%") else orsak)
        return True

    def vänta_på_napp(self):
        """Väntar tills minispelet dyker upp och sköter shake. False = inget napp."""
        läge = self.inst["shake"]
        self.status("Väntar på napp")
        if läge == "navigation":
            self.nav()
        start = time.time()
        senast_klick = 0.0
        kandidat = None
        try:
            while True:
                bild = self.skärm.hämta()
                if bild is not None and hitta_reel(bild):
                    return True
                nu = time.time()
                if nu - start > self.inst["napp_timeout"]:
                    return False
                if läge == "navigation":
                    self.status("Skakar")
                    self.inp.tap(KEY_ENTER)
                    self.vänta(self.slump(0.08, 0.25))
                    continue
                if läge == "klick" and bild is not None:
                    pos = hitta_shake(bild)
                    H, W = bild.shape[:2]
                    # Kräv samma träff i två bilder i rad, så att inget ryck ger felklick.
                    if pos and kandidat and abs(pos[0] - kandidat[0]) < W * 0.02 \
                            and abs(pos[1] - kandidat[1]) < H * 0.02:
                        if nu - senast_klick > self.slump(0.15, 0.3):
                            j = 4 if self.inst["slumpa"] else 0
                            self.status("Skakar")
                            self.inp.flytta((pos[0] + random.uniform(-j, j)) / W,
                                            (pos[1] + random.uniform(-j, j)) / H)
                            self.pekare_flyttad = True
                            time.sleep(0.03)
                            self.inp.tap(BTN_LEFT)
                            senast_klick = nu
                            self.shakes += 1
                            start = nu          # shake = något händer, nollställ timeout
                            kandidat = None
                            self.vänta(0.05)
                            continue
                    kandidat = pos
                self.vänta(0.03)
        finally:
            if läge == "navigation":
                self.nav()

    def cykel(self):
        """En hel fiskerunda. Returnerar 'fångad', 'tappad' eller 'inget napp'."""
        self.shakes = 0
        self.kamptid = 0.0
        self.kasta()
        self.vänta(self.slump(0.6))
        if not self.vänta_på_napp():
            self.diag.inget_napp(self.skärm.hämta())
            return "inget napp"
        self.status("Drar in")
        kampstart = time.time()
        self.diag.kamp_start()
        resultat = self.reel()
        self.kamptid = time.time() - kampstart
        self.diag.kamp_slut(resultat, self.kamptid)
        self.vy = None
        if resultat == "fångad":
            self.vänta(0.4)
            self.diag.fångstbild(self.skärm.hämta())
            self.vänta(self.slump(1.1, 0.2))
        else:
            self.vänta(self.slump(1.5, 0.2))
        return resultat

    def reel(self):
        syn = self.syn
        syn.ny_reel()
        prover = []          # (tid, bar_mitt) för barens hastighet
        fprover = []         # (tid, fisk_x) för fiskens hastighet
        fart_hist = []       # (tid, barens hastighet, håll) för att lära in accelerationen
        håll = False
        fisk_rel = 0.5       # var i baren fisken sågs senast (0 = vänster, 1 = höger)
        senast_mitt = None
        borta_sedan = None
        mörk_sedan = None
        progress = []        # (tid, px)
        max_prog = 0
        sista_läge = None
        start = time.time()

        def resultat_av(orsak):
            """Fångad eller tappad? Avgörs av progressbaren i slutet av kampen."""
            if orsak == "timeout":
                return "tappad"
            nu = time.time()
            senaste = [(t, p) for t, p in progress if nu - t < 1.5]
            if len(senaste) >= 3:
                slut = sorted(p for _, p in senaste[-3:])[1]
                if slut <= 0.06:
                    return "tappad"
                if slut >= 0.85:
                    return "fångad"
                # Annars: steg eller sjönk progressbaren på slutet?
                mitt = len(senaste) // 2
                före = sorted(p for _, p in senaste[:mitt])[mitt // 2] if mitt else slut
                return "fångad" if slut >= före else "tappad"
            return "tappad" if sista_läge == "mörk" else "fångad"

        try:
            while True:
                self.vänta(0)
                nu = time.time()
                if nu - start > 120:
                    return resultat_av("timeout")
                bild = self.skärm.hämta()
                if bild is None:
                    continue
                läge, b0, b1, fisk, prog = syn.läs(bild)
                W = bild.shape[1]
                self.diag.kamp_bild(bild, läge, b0, b1, fisk, prog)

                if läge is None:
                    self.inp.up(BTN_LEFT)
                    borta_sedan = borta_sedan or nu
                    if nu - borta_sedan > 0.35:
                        return resultat_av("borta")
                    time.sleep(0.01)
                    continue
                borta_sedan = None
                sista_läge = läge
                if prog is not None:
                    progress.append((nu, prog))

                if läge == "mörk":
                    mörk_sedan = mörk_sedan or nu
                    if nu - mörk_sedan > self.inst["mörk_max"]:
                        return resultat_av("timeout")
                else:
                    mörk_sedan = None

                if b0 is not None:
                    mitt = (b0 + b1) / 2
                    senast_mitt = mitt
                    prover.append((nu, mitt))
                    prover = prover[-6:]
                self.vy = (b0, b1, fisk, W, läge)

                if fisk is not None:
                    fprover.append((nu, fisk))
                    fprover = fprover[-5:]
                if fisk is not None and b0 is not None:
                    fisk_rel = (fisk - b0) / max(1, b1 - b0)
                    håll = self.styr(prover, fprover, fart_hist, nu, mitt, b1 - b0, fisk, håll)
                elif fisk is not None and senast_mitt is not None:
                    håll = fisk > senast_mitt      # ser fisken men inte baren
                else:
                    håll = fisk_rel > 0.5          # ser inte fisken: jaga åt senaste hållet
                if håll:
                    self.inp.down(BTN_LEFT)
                else:
                    self.inp.up(BTN_LEFT)
                time.sleep(0.005)
        finally:
            self.inp.up(BTN_LEFT)

    def styr(self, prover, fprover, fart_hist, nu, mitt, bredd, fisk, håll_nu):
        """Bromspunkt-styrning: håll inne om baren, efter att ha bromsat in,
        skulle stanna till vänster om där fisken är på väg."""
        v = hastighet(prover[-5:])
        fv = hastighet(fprover)
        if self.acc is None:
            self.acc = 4.0 * bredd
        # Lär in accelerationen: hur fort farten ändras när kommandot legat still.
        fart_hist.append((nu, v, håll_nu))
        del fart_hist[:-12]
        if len(fart_hist) >= 6 and all(h[2] == håll_nu for h in fart_hist[-6:]):
            dt = fart_hist[-1][0] - fart_hist[-6][0]
            if dt > 0.05:
                a = abs(fart_hist[-1][1] - fart_hist[-6][1]) / dt
                if a > 0.5 * bredd:
                    self.acc = 0.85 * self.acc + 0.15 * min(a, 20 * bredd)
        broms = max(-1.5 * bredd, min(1.5 * bredd, v * abs(v) / (2 * self.acc)))
        ledning = max(-0.8 * bredd, min(0.8 * bredd, fv * self.inst["förutsägelse"]))
        return mitt + broms < fisk + ledning

    def anti_afk(self):
        """Roblox kastar ut efter 20 min utan aktivitet. När makrot är pausat
        rörs musen en pixel fram och tillbaka var ~8:e minut."""
        nu = time.time()
        if not self.inst.get("anti_afk") or self.inp is None:
            self.senast_aktiv = nu
            return
        if nu - getattr(self, "senast_aktiv", nu) >= getattr(self, "afk_intervall", 480):
            self.inp.rör(1, 0)
            time.sleep(0.05)
            self.inp.rör(-1, 0)
            self.senast_aktiv = nu
            self.afk_intervall = random.uniform(420, 540)
            self.logg("Anti-AFK: rörde musen (så att Roblox inte kastar ut dig)")
        elif not hasattr(self, "senast_aktiv"):
            self.senast_aktiv = nu

    def loop(self):
        while True:
            if not self.kör.wait(0.1):
                try:
                    self.debug()
                    self.anti_afk()
                except Exception as fel:  # tråden får aldrig dö
                    self.logg(f"Fel: {fel!r}")
                continue
            self.senast_aktiv = time.time()
            try:
                resultat = self.cykel()
                self.diag.resultat(resultat)
                self.q.put(("resultat", (resultat, self.kamptid, self.shakes)))
            except InterruptedError:
                pass
            except Exception as fel:  # håll appen vid liv, visa felet i loggen
                import traceback
                self.logg(f"Fel: {fel!r}")
                ram = traceback.extract_tb(fel.__traceback__)[-1]
                self.logg(f"  (rad {ram.lineno} i {ram.name}: {ram.line})")
                try:
                    self.diag.fel(f"{fel!r} på rad {ram.lineno} i {ram.name}",
                                  self.skärm.hämta() if self.skärm else None)
                except Exception:
                    pass
                self.q.put(("stoppa", f"Fel: {fel}"))
                self.kör.clear()
            finally:
                self.vy = None
                if self.inp:
                    self.inp.release_all()


def hastighet(prover):
    """Robust hastighet (px/s): median av lutningarna mellan alla par (Theil-Sen)."""
    lutningar = []
    for i in range(len(prover)):
        for j in range(i + 1, len(prover)):
            dt = prover[j][0] - prover[i][0]
            if dt > 1e-4:
                lutningar.append((prover[j][1] - prover[i][1]) / dt)
    if not lutningar:
        return 0.0
    lutningar.sort()
    return lutningar[len(lutningar) // 2]


# ---------------------------------------------------------------- App (fönstret)

BG, PANEL, TEXT, DÄMPAD = "#16161e", "#1f2030", "#e6e6f0", "#8a8aa0"
GRÖN, RÖD, GUL, BLÅ = "#4ade80", "#f87171", "#facc15", "#60a5fa"


class App:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.inst = dict(STANDARD)
        self.profiler = {}
        try:
            with open(KONFIG) as f:
                data = json.load(f)
            if "inställningar" in data:
                self.inst.update(data["inställningar"])
                if "nav_kod" not in data["inställningar"]:
                    self.inst["shake"] = "navigation"  # äldre version: byt till UI Navigation
                self.profiler = data.get("profiler", {})
            else:
                self.inst.update(data)  # gammalt format
        except (OSError, ValueError):
            pass
        if self.inst["shake"] in (True, False, "enter"):
            self.inst["shake"] = "navigation"

        self.hist = {"totalt": {}, "rekord": {}, "sessioner": []}
        try:
            with open(STAT_FIL) as f:
                self.hist.update(json.load(f))
        except (OSError, ValueError):
            pass
        self.session = None
        self.svit = 0

        self.q = queue.Queue()
        self.makro = Makro(self.inst, self.q)
        self.stat = {"fångad": 0, "tappad": 0, "inget napp": 0}
        self.fångster = []   # tidpunkter för fångster (för grafen)
        self.start_tid = None
        self.körtid = 0.0
        self.redo = False

        self.root = root = tk.Tk()
        root.title(f"Fisch Makro v{VERSION}")
        root.configure(bg=BG)
        root.geometry("340x720")
        root.minsize(300, 560)
        root.attributes("-topmost", self.inst["överst"])
        self.stil()

        yttre = ttk.Frame(root, padding=(12, 12, 12, 8))
        yttre.pack(fill="both", expand=True)

        # --- Status + start (alltid synligt)
        topp = ttk.Frame(yttre, style="Panel.TFrame", padding=12)
        topp.pack(fill="x")
        self.status_prick = tk.Canvas(topp, width=14, height=14, bg=PANEL, highlightthickness=0)
        self.status_prick.grid(row=0, column=0, padx=(0, 8))
        self.prick = self.status_prick.create_oval(2, 2, 12, 12, fill=DÄMPAD, outline="")
        self.status_text = ttk.Label(topp, text="Startar...", style="Panel.TLabel",
                                     font=("", 13, "bold"))
        self.status_text.grid(row=0, column=1, sticky="w")
        self.steg_text = ttk.Label(topp, text="", style="Dämpad.TLabel")
        self.steg_text.grid(row=1, column=1, columnspan=2, sticky="w")
        self.versions_lbl = ttk.Label(topp, text=f"version {VERSION}", style="Dämpad.TLabel")
        self.versions_lbl.grid(row=0, column=2, sticky="ne")
        topp.columnconfigure(1, weight=1)
        self.startknapp = ttk.Button(yttre, text="Starta  (F6)", style="Start.TButton",
                                     command=self.växla, state="disabled")
        self.startknapp.pack(fill="x", pady=(8, 8))

        self.flikar = flikar = ttk.Notebook(yttre)
        flikar.pack(fill="both", expand=True)
        fiske = ttk.Frame(flikar, padding=(0, 8))
        inst = ttk.Frame(flikar, padding=(0, 8))
        loggflik = ttk.Frame(flikar, padding=(0, 8))
        tavla = ttk.Frame(flikar, padding=(0, 8))
        flikar.add(fiske, text="Fiske")
        flikar.add(tavla, text="Statistik")
        flikar.add(inst, text="Inställningar")
        flikar.add(loggflik, text="Logg")

        self.bygg_fiske(fiske)
        self.bygg_inställningar(inst)
        self.bygg_tavla(tavla)
        self.logg = tk.Text(loggflik, bg=PANEL, fg=TEXT, relief="flat", wrap="word",
                            font=("monospace", 9), state="disabled", highlightthickness=0)
        self.logg.pack(fill="both", expand=True)

        root.protocol("WM_DELETE_WINDOW", self.stäng)
        self.sätt_status("Startar...", DÄMPAD, "Väntar på lösenord och skärmdelning")
        threading.Thread(target=self.starta_tjänster, daemon=True).start()
        threading.Thread(target=self.makro.loop, daemon=True).start()
        self.root.after(3000, lambda: self.sök_uppdatering(tyst=True))
        self.uppdatera()

    def stil(self):
        stil = self.ttk.Style(self.root)
        stil.theme_use("clam")
        stil.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL)
        stil.configure("TFrame", background=BG)
        stil.configure("Panel.TFrame", background=PANEL)
        stil.configure("TLabel", background=BG, foreground=TEXT)
        stil.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        stil.configure("Dämpad.TLabel", background=PANEL, foreground=DÄMPAD)
        stil.configure("Rubrik.TLabel", background=BG, foreground=DÄMPAD, font=("", 9, "bold"))
        stil.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        stil.map("TCheckbutton", background=[("active", PANEL)])
        stil.configure("TSpinbox", arrowcolor=TEXT, foreground=TEXT)
        stil.configure("TCombobox", arrowcolor=TEXT, foreground=TEXT)
        stil.configure("TButton", background=PANEL, foreground=TEXT, borderwidth=0, padding=6)
        stil.map("TButton", background=[("active", "#2b2c40")])
        stil.configure("Start.TButton", font=("", 12, "bold"), padding=10)
        stil.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BG,
                       lightcolor=BG, darkcolor=BG, tabmargins=0)
        stil.configure("TNotebook.Tab", background=BG, foreground=DÄMPAD, padding=(10, 4),
                       bordercolor=BG, lightcolor=BG, darkcolor=BG)
        stil.map("TNotebook.Tab", background=[("selected", PANEL)],
                 foreground=[("selected", TEXT)])

    def bygg_fiske(self, f):
        tk, ttk = self.tk, self.ttk
        ttk.Label(f, text="REEL LIVE", style="Rubrik.TLabel").pack(anchor="w", pady=(0, 4))
        self.vy = tk.Canvas(f, height=50, bg=PANEL, highlightthickness=0)
        self.vy.pack(fill="x")

        ttk.Label(f, text="STATISTIK", style="Rubrik.TLabel").pack(anchor="w", pady=(12, 4))
        sp = ttk.Frame(f, style="Panel.TFrame", padding=10)
        sp.pack(fill="x")
        self.stat_lbl = {}
        rader = [("fångad", "Fångade"), ("tappad", "Tappade"), ("inget napp", "Inget napp"),
                 ("träff", "Träffsäkerhet"), ("tid", "Körtid"), ("takt", "Fiskar / timme")]
        for i, (nyckel, namn) in enumerate(rader):
            ttk.Label(sp, text=namn, style="Dämpad.TLabel").grid(row=i // 2 * 2, column=i % 2,
                                                                 sticky="w", padx=4)
            lbl = ttk.Label(sp, text="0", style="Panel.TLabel", font=("", 14, "bold"))
            lbl.grid(row=i // 2 * 2 + 1, column=i % 2, sticky="w", padx=4, pady=(0, 6))
            self.stat_lbl[nyckel] = lbl
        sp.columnconfigure((0, 1), weight=1)

        ttk.Label(f, text="FÅNGSTER SENASTE TIMMEN", style="Rubrik.TLabel").pack(
            anchor="w", pady=(12, 4))
        self.graf = tk.Canvas(f, height=90, bg=PANEL, highlightthickness=0)
        self.graf.pack(fill="x")

        knappar = ttk.Frame(f)
        knappar.pack(fill="x", pady=(10, 0))
        ttk.Button(knappar, text="Skärmbild (F8)", command=self.skärmbild
                   ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(knappar, text="Nollställ", command=self.nollställ
                   ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def bygg_tavla(self, f):
        tk, ttk = self.tk, self.ttk
        ttk.Label(f, text="ALLA PASS", style="Rubrik.TLabel").pack(anchor="w", pady=(0, 4))
        sp = ttk.Frame(f, style="Panel.TFrame", padding=10)
        sp.pack(fill="x")
        self.tavla_lbl = {}
        rutor = [("tot_fångad", "Fångade totalt"), ("idag", "Fångade idag"),
                 ("tot_tid", "Total körtid"), ("bästa_takt", "Bästa takt (fisk/h)"),
                 ("svit", "Längsta svit"), ("snitt_kamp", "Snitt kamptid"),
                 ("tot_träff", "Träffsäkerhet"), ("tot_shake", "Shake-klick")]
        for i, (nyckel, namn) in enumerate(rutor):
            ttk.Label(sp, text=namn, style="Dämpad.TLabel").grid(row=i // 2 * 2, column=i % 2,
                                                                 sticky="w", padx=4)
            lbl = ttk.Label(sp, text="–", style="Panel.TLabel", font=("", 13, "bold"))
            lbl.grid(row=i // 2 * 2 + 1, column=i % 2, sticky="w", padx=4, pady=(0, 6))
            self.tavla_lbl[nyckel] = lbl
        sp.columnconfigure((0, 1), weight=1)

        ttk.Label(f, text="SENASTE PASSEN", style="Rubrik.TLabel").pack(anchor="w", pady=(12, 4))
        self.pass_lista = tk.Text(f, height=10, bg=PANEL, fg=TEXT, relief="flat",
                                  font=("monospace", 9), state="disabled", highlightthickness=0)
        self.pass_lista.pack(fill="both", expand=True)
        ttk.Button(f, text="Nollställ all statistik", command=self.nollställ_allt
                   ).pack(fill="x", pady=(8, 0))
        self.rita_tavla()

    def spara_hist(self):
        try:
            os.makedirs(os.path.dirname(STAT_FIL), exist_ok=True)
            with open(STAT_FIL, "w") as f:
                json.dump(self.hist, f, indent=1, ensure_ascii=False)
        except OSError:
            pass

    def registrera(self, resultat, kamptid, shakes):
        tot, rek = self.hist["totalt"], self.hist["rekord"]
        tot[resultat] = tot.get(resultat, 0) + 1
        tot["shakes"] = tot.get("shakes", 0) + shakes
        if resultat != "inget napp":
            tot["kamptid"] = tot.get("kamptid", 0) + kamptid
            tot["kamper"] = tot.get("kamper", 0) + 1
        dag = time.strftime("%Y-%m-%d")
        if resultat == "fångad":
            dagar = self.hist.setdefault("dagar", {})
            dagar[dag] = dagar.get(dag, 0) + 1
            for gammal in sorted(dagar)[:-30]:
                del dagar[gammal]
            self.svit += 1
            rek["svit"] = max(rek.get("svit", 0), self.svit)
        elif resultat == "tappad":
            self.svit = 0
        if self.session:
            self.session[resultat] = self.session.get(resultat, 0) + 1
        self.spara_hist()

    def avsluta_session(self):
        if not self.session:
            return
        tid = time.time() - self.session["start"]
        self.session["tid"] = tid
        tot, rek = self.hist["totalt"], self.hist["rekord"]
        tot["tid"] = tot.get("tid", 0) + tid
        f = self.session.get("fångad", 0)
        if tid >= 600 and f:
            rek["takt"] = max(rek.get("takt", 0), f / tid * 3600)
        if tid >= 30:
            self.hist["sessioner"] = (self.hist["sessioner"] + [self.session])[-50:]
        self.session = None
        self.spara_hist()
        self.rita_tavla()

    def nollställ_allt(self):
        from tkinter import messagebox
        if messagebox.askyesno("Nollställ", "Radera all sparad statistik?", parent=self.root):
            self.hist = {"totalt": {}, "rekord": {}, "sessioner": []}
            self.svit = 0
            self.spara_hist()
            self.rita_tavla()
            self.skriv("All statistik nollställd")

    def rita_tavla(self):
        tot, rek = self.hist["totalt"], self.hist["rekord"]
        pågår = time.time() - self.session["start"] if self.session else 0
        f, t = tot.get("fångad", 0), tot.get("tappad", 0)
        tid = tot.get("tid", 0) + pågår
        h, rest = divmod(int(tid), 3600)
        takt = rek.get("takt", 0)
        if self.session and pågår >= 600:
            takt = max(takt, self.session.get("fångad", 0) / pågår * 3600)
        värden = {
            "tot_fångad": str(f),
            "idag": str(self.hist.get("dagar", {}).get(time.strftime("%Y-%m-%d"), 0)),
            "tot_tid": f"{h} h {rest // 60} min",
            "bästa_takt": f"{takt:.0f}" if takt else "–",
            "svit": str(rek.get("svit", 0)),
            "snitt_kamp": f"{tot['kamptid'] / tot['kamper']:.1f} s" if tot.get("kamper") else "–",
            "tot_träff": f"{100 * f / (f + t):.0f} %" if f + t else "–",
            "tot_shake": str(tot.get("shakes", 0)),
        }
        for nyckel, text in värden.items():
            self.tavla_lbl[nyckel].config(text=text)
        rader = [f"{'Datum':<12}{'Tid':<9}{'Fisk':>5}{'/h':>6}{'Träff':>7}"]
        for p in reversed(self.hist["sessioner"][-15:]):
            pt = p.get("tid", 0)
            pf, ptp = p.get("fångad", 0), p.get("tappad", 0)
            rader.append(f"{time.strftime('%d/%m %H:%M', time.localtime(p['start'])):<12}"
                         f"{int(pt // 3600)}:{int(pt % 3600 // 60):02d}:{int(pt % 60):02d}  "
                         f"{pf:>5}{(pf / pt * 3600 if pt else 0):>6.0f}"
                         f"{(f'{100 * pf / (pf + ptp):.0f}%' if pf + ptp else '–'):>7}")
        if len(rader) == 1:
            rader.append("Inga pass sparade än.")
        self.pass_lista.config(state="normal")
        self.pass_lista.delete("1.0", "end")
        self.pass_lista.insert("end", "\n".join(rader))
        self.pass_lista.config(state="disabled")

    def bygg_inställningar(self, f):
        tk, ttk = self.tk, self.ttk
        # Profiler
        ttk.Label(f, text="UPPDATERING", style="Rubrik.TLabel").pack(anchor="w", pady=(0, 4))
        up = ttk.Frame(f, style="Panel.TFrame", padding=10)
        up.pack(fill="x")
        self.uppd_text = ttk.Label(up, text=f"Du har version {VERSION}", style="Panel.TLabel")
        self.uppd_text.pack(anchor="w")
        self.uppd_knapp = ttk.Button(up, text="Sök efter uppdatering", command=self.sök_uppdatering)
        self.uppd_knapp.pack(fill="x", pady=(6, 0))
        self.ny_version = None

        ttk.Label(f, text="PROFIL", style="Rubrik.TLabel").pack(anchor="w", pady=(12, 4))
        pp = ttk.Frame(f, style="Panel.TFrame", padding=10)
        pp.pack(fill="x")
        self.profil_var = tk.StringVar()
        self.profil_box = ttk.Combobox(pp, textvariable=self.profil_var, state="readonly",
                                       values=sorted(self.profiler))
        self.profil_box.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.profil_box.bind("<<ComboboxSelected>>", lambda _e: self.ladda_profil())
        ttk.Button(pp, text="Spara som...", command=self.spara_profil
                   ).grid(row=1, column=0, sticky="ew", pady=(6, 0), padx=(0, 3))
        ttk.Button(pp, text="Ta bort", command=self.ta_bort_profil
                   ).grid(row=1, column=1, sticky="ew", pady=(6, 0), padx=(3, 0))
        pp.columnconfigure((0, 1), weight=1)

        ttk.Label(f, text="FISKE", style="Rubrik.TLabel").pack(anchor="w", pady=(12, 4))
        ip = ttk.Frame(f, style="Panel.TFrame", padding=10)
        ip.pack(fill="x")
        self.vars = {}
        rad = 0
        ttk.Label(ip, text="Shake", style="Panel.TLabel").grid(row=rad, column=0, sticky="w")
        var = tk.StringVar(value=self.inst["shake"])
        box = ttk.Combobox(ip, textvariable=var, values=["navigation", "klick", "av"],
                           state="readonly", width=10)
        box.grid(row=rad, column=1, sticky="e", pady=2)
        box.bind("<<ComboboxSelected>>", lambda _e, v=var: self.sätt("shake", v.get()))
        self.vars["shake"] = var
        rad += 1
        ttk.Label(ip, text="UI Navigation-tangent", style="Panel.TLabel").grid(
            row=rad, column=0, sticky="w")
        self.nav_knapp = ttk.Button(ip, text=tangentnamn(self.inst["nav_kod"]), width=10,
                                    command=self.lär_nav)
        self.nav_knapp.grid(row=rad, column=1, sticky="e", pady=2)
        rad += 1
        fält = [("cast_tid", "Kasttid (s)", 0.1, 3.0, 0.05),
                ("förutsägelse", "Förutsägelse (s)", 0.0, 0.5, 0.01),
                ("mörk_max", "Max tid utanför baren (s)", 0.5, 15.0, 0.5),
                ("napp_timeout", "Kasta om efter (s)", 5, 120, 5),
                ("stopp_fiskar", "Max fiskar (0 = av)", 0, 10000, 1),
                ("stopp_minuter", "Max minuter (0 = av)", 0, 1440, 5)]
        for nyckel, namn, lo, hi, steg in fält:
            ttk.Label(ip, text=namn, style="Panel.TLabel").grid(row=rad, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=str(self.inst[nyckel]))
            ttk.Spinbox(ip, from_=lo, to=hi, increment=steg, textvariable=var, width=7
                        ).grid(row=rad, column=1, sticky="e", pady=2)
            var.trace_add("write", lambda *_a, n=nyckel, v=var: self.sätt(n, v.get()))
            self.vars[nyckel] = var
            rad += 1
        for nyckel, namn in [("perfekt_kast", "Perfekt kast (följer kastmätaren)"),
                             ("slumpa", "Slumpa tider lite (ser mänskligt ut)"),
                             ("anti_afk", "Anti-AFK när pausad (inget idle-kick)"),
                             ("notiser", "Notis + ljud när den stoppar"),
                             ("överst", "Fönstret alltid överst")]:
            var = tk.BooleanVar(value=self.inst[nyckel])
            ttk.Checkbutton(ip, text=namn, variable=var,
                            command=lambda n_=nyckel, v=var: self.sätt(n_, v.get())
                            ).grid(row=rad, column=0, columnspan=2, sticky="w", pady=2)
            self.vars[nyckel] = var
            rad += 1
        ip.columnconfigure(0, weight=1)

        ttk.Label(f, text="DIAGNOSTIK", style="Rubrik.TLabel").pack(anchor="w", pady=(12, 4))
        dg = ttk.Frame(f, style="Panel.TFrame", padding=10)
        dg.pack(fill="x")
        dvar = tk.BooleanVar(value=self.inst["diagnostik"])
        ttk.Checkbutton(dg, text="Spara bilder + rapport (för förbättringar)", variable=dvar,
                        command=lambda: self.sätt("diagnostik", dvar.get())).pack(anchor="w")
        self.vars["diagnostik"] = dvar
        ttk.Label(dg, text="GitHub-token (laddar upp automatiskt)", style="Dämpad.TLabel").pack(
            anchor="w", pady=(6, 0))
        tvar = tk.StringVar(value=self.inst["gh_token"])
        ttk.Entry(dg, textvariable=tvar, show="•").pack(fill="x", pady=(4, 0))
        tvar.trace_add("write", lambda *_a: self.sätt("gh_token", tvar.get().strip()))
        self.diag_text = ttk.Label(dg, text="", style="Dämpad.TLabel")
        self.diag_text.pack(anchor="w", pady=(6, 0))
        ttk.Button(dg, text="Öppna diagnostikmappen", command=self.öppna_diagnostik
                   ).pack(fill="x", pady=(6, 0))

        ttk.Label(f, text="DISCORD (VALFRITT)", style="Rubrik.TLabel").pack(anchor="w", pady=(12, 4))
        dp = ttk.Frame(f, style="Panel.TFrame", padding=10)
        dp.pack(fill="x")
        ttk.Label(dp, text="Webhook-länk (notis vid stopp + varje timme)",
                  style="Dämpad.TLabel").pack(anchor="w")
        var = tk.StringVar(value=self.inst["discord"])
        ttk.Entry(dp, textvariable=var).pack(fill="x", pady=(4, 0))
        var.trace_add("write", lambda *_a, v=var: self.sätt("discord", v.get().strip()))
        ttk.Button(dp, text="Skicka test", command=lambda: self.discord("Test från Fisch Makro 🎣")
                   ).pack(fill="x", pady=(6, 0))

    # ---- bakgrund
    def starta_tjänster(self):
        try:
            self.q.put(("logg", f"Fisch Makro version {VERSION}"))
            self.q.put(("logg", "Frågar efter lösenord..."))
            self.makro.inp = Input(lambda namn: self.q.put(("tangent", namn)))
            self.q.put(("logg", "Välj skärmen med Roblox om en ruta dyker upp."))
            self.makro.skärm = Skärm()
            self.q.put(("redo", None))
        except Exception as fel:
            self.q.put(("fel", str(fel)))

    # ---- inställningar och profiler
    def sätt(self, nyckel, värde):
        if isinstance(värde, str) and nyckel not in ("shake", "discord", "gh_token"):
            try:
                värde = float(värde.replace(",", "."))
            except ValueError:
                return
            if nyckel in ("stopp_fiskar", "stopp_minuter"):
                värde = int(värde)
        self.inst[nyckel] = värde
        if nyckel == "överst":
            self.root.attributes("-topmost", värde)
        self.spara_konfig()

    def spara_konfig(self):
        try:
            os.makedirs(os.path.dirname(KONFIG), exist_ok=True)
            with open(KONFIG, "w") as f:
                json.dump({"inställningar": self.inst, "profiler": self.profiler}, f,
                          indent=2, ensure_ascii=False)
        except OSError:
            pass

    def spara_profil(self):
        from tkinter import simpledialog
        namn = simpledialog.askstring("Spara profil", "Namn på profilen (t.ex. spöets namn):",
                                      parent=self.root)
        if not namn:
            return
        self.profiler[namn] = {k: v for k, v in self.inst.items() if k != "överst"}
        self.profil_box.config(values=sorted(self.profiler))
        self.profil_var.set(namn)
        self.spara_konfig()
        self.skriv(f"Sparade profilen '{namn}'")

    def ladda_profil(self):
        namn = self.profil_var.get()
        for nyckel, värde in self.profiler.get(namn, {}).items():
            if nyckel in self.vars:
                self.vars[nyckel].set(värde)
            self.inst[nyckel] = värde
        self.spara_konfig()
        self.skriv(f"Laddade profilen '{namn}'")

    def ta_bort_profil(self):
        namn = self.profil_var.get()
        if namn in self.profiler:
            del self.profiler[namn]
            self.profil_box.config(values=sorted(self.profiler))
            self.profil_var.set("")
            self.spara_konfig()
            self.skriv(f"Tog bort profilen '{namn}'")

    # ---- start/stopp
    def växla(self):
        if not self.redo:
            return
        if self.makro.kör.is_set():
            self.stoppa()
        else:
            self.start_tid = time.time()
            self.session = {"start": time.time()}
            self.makro.kör.set()
            self.startknapp.config(text="Stoppa  (F6)")
            self.sätt_status("Fiskar", GRÖN, "")
            self.skriv("▶ Startad")

    def stoppa(self, orsak="Stoppad", meddela=False):
        if self.start_tid:
            self.körtid += time.time() - self.start_tid
            self.start_tid = None
        self.makro.kör.clear()
        if self.makro.inp:
            self.makro.inp.release_all()
        self.avsluta_session()
        self.startknapp.config(text="Starta  (F6)")
        self.sätt_status("Stoppad", RÖD, orsak if meddela else "Tryck F6 i spelet för att starta")
        self.skriv(f"■ {orsak}")
        if meddela and self.inst["notiser"]:
            notis(orsak)
        if meddela:
            self.discord(f"■ Fisch Makro stoppade: {orsak}\n{self.sammanfattning()}")

    def skärmbild(self):
        self.skriv("F8: sparar skärmbild...")
        self.makro.spara.set()

    def sök_uppdatering(self, tyst=False):
        """Kollar om det finns en nyare version. Klick igen när en finns = installera."""
        if self.ny_version:
            return self.installera_uppdatering()
        self.uppd_knapp.config(state="disabled", text="Söker...")

        def jobb():
            try:
                ver, kod = hämta_senaste()
                self.q.put(("uppdatering", (ver, kod, tyst)))
            except Exception as fel:
                self.q.put(("uppdatering", (None, str(fel), tyst)))
        threading.Thread(target=jobb, daemon=True).start()

    def uppdatering_klar(self, ver, kod, tyst):
        self.uppd_knapp.config(state="normal", text="Sök efter uppdatering")
        if ver is None:
            if not tyst:
                self.uppd_text.config(text=f"Kunde inte söka: {kod}"[:60])
                self.skriv(f"Uppdatering: kunde inte söka ({kod})")
            return
        if versionstal(ver) > versionstal(VERSION):
            self.ny_version = (ver, kod)
            self.uppd_text.config(text=f"Version {ver} finns! (du har {VERSION})")
            self.uppd_knapp.config(text=f"Installera version {ver}")
            self.versions_lbl.config(text=f"v{ver} finns!", foreground=GUL)
            self.skriv(f"Ny version {ver} finns - Inställningar → Installera.")
        elif not tyst:
            self.uppd_text.config(text=f"Du har senaste versionen ({VERSION})")
            self.skriv(f"Uppdatering: du har redan senaste versionen ({VERSION}).")

    def installera_uppdatering(self):
        ver, kod = self.ny_version
        mål = os.path.abspath(__file__)
        try:
            with open(mål + ".ny", "w", encoding="utf-8") as fil:
                fil.write(kod)
            shutil.copy2(mål, mål + ".gammal")      # backup av nuvarande version
            os.replace(mål + ".ny", mål)
        except OSError as fel:
            self.skriv(f"Uppdatering misslyckades: {fel}")
            self.uppd_text.config(text="Uppdatering misslyckades, se loggen")
            return
        self.skriv(f"Installerade version {ver} - startar om...")
        self.uppd_text.config(text=f"Version {ver} installerad - startar om...")
        self.root.after(800, self.starta_om)

    def starta_om(self):
        self.stäng()
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])

    def öppna_diagnostik(self):
        mapp = os.path.join(MAPP, "diagnostik")
        os.makedirs(mapp, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", mapp])
        except OSError:
            self.skriv(f"Diagnostiken ligger i {mapp}")

    def rita_diagnostik(self):
        d = self.makro.diag
        sam = d.sammanfattning()
        text = f"Pass {d.pass_id[9:11]}:{d.pass_id[11:13]}: {sam['fångad']} fångade, {sam['tappad']} tappade"
        if sam["fisk_i_baren"] is not None:
            text += f", fisk i baren {sam['fisk_i_baren']:.0%}"
        if self.inst.get("gh_token"):
            text += f"\nUppladdat: {d.uppladdat} filer" + (f" (senast {d.senast_uppladdat})"
                                                          if d.senast_uppladdat else "")
        self.diag_text.config(text=text)

    def lär_nav(self):
        if not self.makro.inp:
            self.skriv("Vänta tills appen är redo.")
            return
        self.lär_väntar = True
        self.nav_knapp.config(text="tryck nu...")
        self.skriv("Tryck tangenten du använder för UI Navigation i Roblox.")
        self.makro.inp.lär()

    def discord(self, text):
        """Skickar ett meddelande till Discord-webhooken (i bakgrunden)."""
        url = self.inst.get("discord", "")
        if not url.startswith("https://"):
            return

        def skicka():
            import urllib.request
            try:
                req = urllib.request.Request(
                    url, data=json.dumps({"content": text}).encode(),
                    headers={"Content-Type": "application/json", "User-Agent": "FischMakro"})
                urllib.request.urlopen(req, timeout=10).close()
            except Exception as fel:
                self.q.put(("logg", f"Discord-fel: {fel}"))
        threading.Thread(target=skicka, daemon=True).start()

    def sammanfattning(self):
        f, t = self.stat["fångad"], self.stat["tappad"]
        tid = self.körtid + (time.time() - self.start_tid if self.start_tid else 0)
        takt = f"{f / tid * 3600:.0f}/h" if tid > 60 else "–"
        return f"🐟 {f} fångade, ✗ {t} tappade, {int(tid // 60)} min, {takt}"

    def nollställ(self):
        self.stat = {k: 0 for k in self.stat}
        self.fångster = []
        self.körtid = 0.0
        if self.start_tid:
            self.start_tid = time.time()
        self.skriv("Statistik nollställd")

    # ---- gränssnitt
    def sätt_status(self, text, färg, steg):
        self.status_text.config(text=text)
        self.status_prick.itemconfig(self.prick, fill=färg)
        self.steg_text.config(text=steg)

    def skriv(self, text):
        self.logg.config(state="normal")
        self.logg.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
        rader = int(self.logg.index("end-1c").split(".")[0])
        if rader > 300:
            self.logg.delete("1.0", f"{rader - 300}.0")
        self.logg.see("end")
        self.logg.config(state="disabled")

    def rita_vy(self):
        c = self.vy
        c.delete("all")
        w = c.winfo_width()
        c.create_rectangle(8, 12, w - 8, 34, fill="#0e0e16", outline="#33344a")
        sk = self.makro.skärm
        if sk is not None and hasattr(sk, "bilder_per_s"):
            bps = sk.bilder_per_s()
            c.create_text(w - 8, 42, text=f"skärm {bps:.0f} bilder/s", anchor="e",
                          fill=RÖD if bps < 5 else DÄMPAD, font=("", 7))
        vy = self.makro.vy
        if not vy:
            c.create_text(w / 2, 23, text="ingen reel just nu", fill=DÄMPAD)
            return
        b0, b1, fisk, bredd, läge = vy
        a, b = REEL_OMRÅDE[0] * bredd, REEL_OMRÅDE[2] * bredd

        def x(v):
            return 8 + (v - a) / (b - a) * (w - 16)
        mörk = läge == "mörk"
        if b0 is not None:
            c.create_rectangle(x(b0), 12, x(b1), 34, fill="#555566" if mörk else "#d8d8e0",
                               outline="")
        if fisk is not None:
            c.create_rectangle(x(fisk) - 2, 8, x(fisk) + 2, 38, fill=RÖD if mörk else BLÅ,
                               outline="")
        if mörk:
            c.create_text(w / 2, 5, text="fisken utanför - jagar", fill=GUL, font=("", 7))

    def rita_graf(self):
        c = self.graf
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        nu = time.time()
        hinkar = [0] * 12   # 12 x 5 minuter
        for t in self.fångster:
            i = int((nu - t) // 300)
            if 0 <= i < 12:
                hinkar[11 - i] += 1
        top = max(hinkar + [1])
        bw = (w - 16) / 12
        for i, n in enumerate(hinkar):
            hh = (h - 26) * n / top
            x0 = 8 + i * bw
            c.create_rectangle(x0 + 2, h - 16 - hh, x0 + bw - 2, h - 16,
                               fill=GRÖN if n else "#2b2c40", outline="")
            if n:
                c.create_text(x0 + bw / 2, h - 22 - hh, text=str(n), fill=TEXT, font=("", 7))
        c.create_text(8, h - 7, text="-60 min", fill=DÄMPAD, anchor="w", font=("", 7))
        c.create_text(w - 8, h - 7, text="nu", fill=DÄMPAD, anchor="e", font=("", 7))

    def uppdatera_stat(self):
        tid = self.körtid + (time.time() - self.start_tid if self.start_tid else 0)
        f, t = self.stat["fångad"], self.stat["tappad"]
        self.stat_lbl["fångad"].config(text=str(f), foreground=GRÖN)
        self.stat_lbl["tappad"].config(text=str(t), foreground=RÖD)
        self.stat_lbl["inget napp"].config(text=str(self.stat["inget napp"]))
        self.stat_lbl["träff"].config(text=f"{100 * f / (f + t):.0f} %" if f + t else "–")
        h, rest = divmod(int(tid), 3600)
        self.stat_lbl["tid"].config(text=f"{h}:{rest // 60:02d}:{rest % 60:02d}")
        self.stat_lbl["takt"].config(text=f"{f / tid * 3600:.0f}" if tid > 60 else "–")
        return tid

    def uppdatera(self):
        try:
            while True:
                typ, data = self.q.get_nowait()
                if typ == "logg":
                    self.skriv(data)
                elif typ == "status":
                    if self.makro.kör.is_set():
                        self.steg_text.config(text=data + "...")
                elif typ == "resultat":
                    data, kamptid, shakes = data
                    self.registrera(data, kamptid, shakes)
                    self.stat[data] += 1
                    if data == "fångad":
                        self.fångster.append(time.time())
                    ikon = {"fångad": "🐟 Fångad!", "tappad": "✗ Tappad",
                            "inget napp": "… Inget napp, kastar om"}[data]
                    self.skriv(ikon)
                    mål = self.inst["stopp_fiskar"]
                    if mål and self.stat["fångad"] >= mål:
                        self.stoppa(f"Klar, {mål} fiskar fångade", meddela=True)
                elif typ == "stoppa":
                    self.stoppa(data, meddela=True)
                elif typ == "tangent":
                    if data.startswith("TANGENT"):
                        kod = int(data.split()[1])
                        self.sätt("nav_kod", kod)
                        self.nav_knapp.config(text=tangentnamn(kod))
                        self.skriv(f"UI Navigation-tangent: {tangentnamn(kod)}")
                    elif data == "F6":
                        self.växla()
                    elif data == "ESC" and self.makro.kör.is_set():
                        self.stoppa()
                    elif data == "F8":
                        self.skärmbild()
                elif typ == "redo":
                    self.redo = True
                    self.startknapp.config(state="normal")
                    self.sätt_status("Redo", GUL, "Klicka in i Roblox och tryck F6")
                    self.skriv("Redo! Ställ musen mitt i spelet och tryck F6.")
                elif typ == "uppdatering":
                    self.uppdatering_klar(*data)
                elif typ == "fel":
                    self.sätt_status("Fel", RÖD, data)
                    self.skriv(f"Fel: {data}")
        except queue.Empty:
            pass
        tid = self.uppdatera_stat()
        minuter = self.inst["stopp_minuter"]
        if minuter and self.start_tid and tid >= minuter * 60:
            self.stoppa(f"Tiden är ute ({minuter} min)", meddela=True)
        self.rita_vy()
        self.rita_graf()
        if self.start_tid and time.time() - getattr(self, "senaste_rapport", 0) > 3600:
            if getattr(self, "senaste_rapport", 0):
                self.discord("⏱ Timrapport: " + self.sammanfattning())
            self.senaste_rapport = time.time()
        self.tick = getattr(self, "tick", 0) + 1
        if self.tick % 20 == 0:
            self.rita_tavla()
            self.rita_diagnostik()
            sk = self.makro.skärm
            if self.makro.kör.is_set() and sk is not None and hasattr(sk, "bilder_per_s"):
                self.makro.diag.spara_rapport(bps=sk.bilder_per_s())
        self.root.after(50, self.uppdatera)

    def stäng(self):
        self.avsluta_session()
        self.makro.kör.clear()
        if self.makro.inp:
            self.makro.inp.stäng()
        self.root.destroy()

    def kör(self):
        self.root.mainloop()


def saknade_paket():
    saknas = []
    for mod in ("numpy", "gi", "evdev", "tkinter"):
        try:
            __import__(mod)
        except ImportError:
            saknas.append(mod)
    if "gi" not in saknas:
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst  # noqa: F401
        except (ImportError, ValueError):
            saknas.append("gstreamer")
    return saknas


def main():
    if os.geteuid() == 0:
        sys.exit("Starta utan sudo: python3 fisch_app.py")
    if saknade_paket():
        print("Installerar det som saknas...")
        subprocess.run(root_kommando(["apt-get", "install", "-y"] + PAKET), check=False)
        if saknade_paket():
            sys.exit("Kunde inte installera allt. Kör: sudo apt install -y " + " ".join(PAKET))
        os.execv(sys.executable, [sys.executable] + sys.argv)
    App().kör()


if __name__ == "__main__":
    main()
