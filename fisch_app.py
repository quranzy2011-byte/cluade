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

VERSION = "3.5"   # höj vid varje ny version så att man ser vilken man kör
UPPDATERA_URL = "https://raw.githubusercontent.com/quranzy2011-byte/cluade/main/fisch_app.py"
GITHUB_API = "https://api.github.com"
DIAG_REPO = "quranzy2011-byte/cluade-2"   # privat repo dit diagnostiken laddas upp
DIAG_GREN = "diagnostik"

MAPP = os.path.dirname(os.path.abspath(__file__))
KONFIG = os.path.expanduser("~/.config/fisch-makro/installningar.json")
STAT_FIL = os.path.expanduser("~/.config/fisch-makro/statistik.json")
FÅNGST_FIL = os.path.expanduser("~/.config/fisch-makro/fangster.json")
PRISER_FIL = os.path.expanduser("~/.config/fisch-makro/fiskpriser.json")
PRISER_URL = "https://raw.githubusercontent.com/quranzy2011-byte/cluade/main/fiskpriser.json"
# Kända mutationer (prefix före fiskens namn i "You just caught a Shiny Mullet").
# Prislistan (fiskpriser.json) kan lägga till fler och ger deras multiplikatorer.
MUTATIONER = ["Shiny", "Sparkling", "Albino", "Darkened", "Negative", "Translucent", "Electric",
              "Frozen", "Glossy", "Silver", "Mosaic", "Hexed", "Abyssal", "Lunar", "Solarblaze",
              "Fossilized", "Midas", "Ghastly", "Amber", "Scorched", "Aurora", "Atlantean",
              "Sinister", "Nuclear", "Studded", "Crystalized", "Revitalized", "Greedy",
              "Anomalous", "Sandy", "Blighted", "Heavenly", "Unsure", "Subspace", "Quantum",
              "Glitched", "Wrath", "Seasonal", "Oscar", "Mythical", "Celestial",
              "Tentacle Surge", "Nova",
              "Tiny", "Small", "Big", "Giant"]      # storlek: påverkar bara vikten

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
REEL_OMRÅDE = (0.20, 0.74, 0.80, 0.97)   # x0, y0, x1, y1 som andel av skärmen
SHAKE_OMRÅDE = (0.05, 0.15, 0.95, 0.90)  # där shake-knapparna kan dyka upp (inte Robloxknapparna överst)

KEY_ENTER, BTN_LEFT = 28, 272

PAKET = ["python3-evdev", "python3-numpy", "python3-gi", "python3-tk", "gir1.2-gstreamer-1.0",
         "gir1.2-gst-plugins-base-1.0", "gstreamer1.0-pipewire", "tesseract-ocr"]

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
    # Baren är ~40 px hög i 1080p; progressbaren och textrader är lägre.
    if len(band) < max(6, H * 0.025):
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
    # Baren är nästan helt ljus (bara pilar och fisken är mörka). Menyer och
    # verktygsfältet har mest mörka rutor med lite ljus text.
    if andel[b0:b1 + 1].mean() < 0.55:
        return None
    # En riktig bar är kritvit och ligger i ett mörkt spår: tydligt mörkare på
    # sidorna. (Verktygsfältets rutor och suddiga menyer är gråvita och har ljust
    # bredvid sig.)
    inne = float(np.median(lo[ra:rb, b0:b1 + 1]))
    sidor = [float(lo[ra:rb, a:b].mean()) for a, b in ((max(0, b0 - 40), b0 - 4),
                                                         (b1 + 5, min(rw, b1 + 41))) if b - a >= 4]
    if inne < 200 or (sidor and inne - max(sidor) < 70):
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


def läs_progress(bild, rb, bandhöjd, x0, x1, geo=None, väntad=None):
    """Hur full progressbaren under spåret är (0-1), eller None om den inte syns.

    Progressbaren har en vit ram; ramens längd = full bar, den vita
    fyllningen från vänster = hur långt fångsten har kommit.
    geo (dict) får ramens läge (y, vänster, höger); väntad = ett sådant läge
    som ramen måste stämma med (annars är det något annat, t.ex. verktygsfältet)."""
    import numpy as np
    H = bild.shape[0]
    ya, yb = min(H, rb + max(2, int(bandhöjd * 0.2))), min(H, rb + int(bandhöjd * 3))
    if yb - ya < 2:
        return None
    lo = _lo_hi(bild[ya:yb, x0:x1])[0]
    W = bild.shape[1]

    def rimlig(r):
        """Progressbaren sitter mitt på skärmen, en bit under spåret."""
        if r is None:
            return False
        mitt = x0 + (r[2] + r[3]) / 2
        bredd = r[3] - r[2]
        # Exakt centrerad (en fyllning som slutar före ramens högerkant är det inte).
        return (abs(mitt - W / 2) <= max(6, 0.004 * W) and 0.1 * W <= bredd <= 0.45 * W
                and 0.4 * bandhöjd <= r[0] + (ya - rb) <= 1.4 * bandhöjd)

    def para(kanter):
        """Ramen = två kanter (övre och nedre) med samma vänster- och högerände."""
        bäst = None
        for i, (ya_, va, ha) in enumerate(kanter):
            for yb_, vb, hb in kanter[i + 1:]:
                if 3 <= yb_ - ya_ <= 30 and abs(va - vb) <= 4 and abs(ha - hb) <= 4:
                    r = (ya_, yb_, min(va, vb), max(ha, hb))
                    if rimlig(r) and (bäst is None or r[3] - r[2] > bäst[3] - bäst[2]):
                        bäst = r
        return bäst

    # 1) Kanter = rader där ljusa pixlar täcker det mesta av bredden (mörk bakgrund).
    kanter = []
    for i, rad in enumerate(lo):
        xs = np.flatnonzero(rad >= 100)
        if len(xs) > 10 and len(xs) >= 0.5 * (xs[-1] - xs[0]):
            kanter.append((i, xs[0], xs[-1]))
    ram = para(kanter)
    if ram is None:
        # 2) Ljus bakgrund (sand, snö): kanten = tunn linje som är ljusare än
        #    raderna ovanför/under; längsta täta sträckan på raden.
        utökad = _lo_hi(bild[max(0, ya - 2):min(H, yb + 2), x0:x1])[0].astype(np.int16)
        f = ya - max(0, ya - 2)
        kanter = []
        for i, rad in enumerate(lo):
            j = i + f
            if j - 2 < 0 or j + 2 >= len(utökad):
                continue
            grannar = np.minimum(utökad[j - 2], utökad[j + 2])
            xs = np.flatnonzero((rad >= 100) & (rad.astype(np.int16) - grannar >= 35))
            if len(xs) <= 10:
                continue
            bit = max(_körningar(xs, 12), key=len)
            if len(bit) > 10 and len(bit) >= 0.5 * (bit[-1] - bit[0]):
                kanter.append((i, int(bit[0]), int(bit[-1])))
        ram = para(kanter)
    if ram is None:
        return None
    topp, botten, vä, hö = ram
    if väntad is not None and (abs(topp + ya - väntad[0]) > 4 or abs(vä + x0 - väntad[1]) > 8
                               or abs(hö + x0 - väntad[2]) > 8):
        return None
    total = hö - vä
    if total < max(40, bandhöjd * 2, bild.shape[1] * 0.1):
        return None
    # Riktig ram: vita sidokanter på raderna mellan övre och nedre kanten.
    inne = lo[topp + 1:botten]
    sidor = ((inne[:, max(0, vä - 1):vä + 2] >= 100).any(axis=1).mean(),
             (inne[:, max(0, hö - 1):hö + 2] >= 100).any(axis=1).mean())
    if min(sidor) < 0.7:
        return None
    if geo is not None:
        geo["ram"] = (int(topp + ya), int(vä + x0), int(hö + x0))
        geo["botten"] = int(botten + ya)
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


def läs_fyllning(bild, ram):
    """Progress (0-1) i en känd ram (topp, botten, vänster, höger), eller None
    om ramen inte syns där längre. Robust mot annat ljust bredvid ramen."""
    import numpy as np
    topp, botten, vä, hö = ram
    H, W = bild.shape[:2]
    if not (0 <= topp < botten < H and 0 <= vä < hö < W) or botten - topp < 3:
        return None
    lo = _lo_hi(bild[topp:botten + 1, vä:hö + 1])[0]
    total = hö - vä
    # Ramen ska finnas kvar: övre och nedre kanten mest ljusa, sidorna ljusa.
    kant = (lo[0:2] >= 100).mean(axis=1).max() >= 0.45 and \
        (lo[-2:] >= 100).mean(axis=1).max() >= 0.45
    sidor = min((lo[1:-1, :3] >= 100).any(axis=1).mean(), (lo[1:-1, -3:] >= 100).any(axis=1).mean())
    if not kant or sidor < 0.7:
        return None
    fyllning = []
    for rad in lo[1:-1]:
        xs = np.flatnonzero(rad >= 140)
        n = 0
        if len(xs) and xs[0] <= 3:
            n = int(_körningar(xs, 8)[0][-1])
            if n >= total - 3 and len(xs) < 0.9 * total:
                n = 0
        fyllning.append(n)
    return min(1.0, float(np.median(fyllning)) / total)


def hitta_kastmätare(bild):
    """Kastmätaren i vanlig storlek, annars den lilla (kameran långt bort)."""
    return _hitta_stor_kastmätare(bild) or hitta_liten_kastmätare(bild)


def _hitta_stor_kastmätare(bild):
    """Hittar kastmätaren: ett smalt lodrätt rör bredvid gubben (två tunna mörka
    kantlinjer, grön topp) som fylls med vitt nerifrån.
    Returnerar (andel 0-1, x) eller None."""
    import numpy as np
    H, W = bild.shape[:2]
    x0, x1, y0, y1 = int(0.30 * W), int(0.80 * W), int(0.20 * H), int(0.88 * H)
    hi = bild[y0:y1, x0:x1].max(axis=2).astype(np.int16)
    # Kantlinje = tunn mörk "dal": tydligt mörkare än 2 px till vänster och höger.
    dal = np.zeros(hi.shape, bool)
    dal[:, 2:-2] = (hi[:, 2:-2] < hi[:, :-4] - 15) & (hi[:, 2:-2] < hi[:, 4:] - 15) & \
        (hi[:, 2:-2] < 120)
    dal[:, 1:] |= dal[:, :-1]          # tillåt att linjen vickar en pixel
    minst = int(0.08 * H)
    kol = np.flatnonzero(dal.sum(axis=0) >= minst)
    if len(kol) < 2:
        return None

    def sträcka(x):
        rader = np.flatnonzero(dal[:, x])
        if len(rader) == 0:
            return None
        run = max(_körningar(rader, 10), key=len)   # tål glapp (randig bakgrund)
        return (int(run[0]), int(run[-1])) if run[-1] - run[0] >= minst else None

    sträckor = {int(x): sträcka(x) for x in kol}
    bäst = None
    for xv in kol:
        a = sträckor[int(xv)]
        if a is None:
            continue
        for xh in kol[(kol >= xv + 5) & (kol <= xv + 16)]:
            b = sträckor[int(xh)]
            if b is None or abs(a[0] - b[0]) > 8 or abs(a[1] - b[1]) > 8:
                continue
            topp, botten = max(a[0], b[0]), min(a[1], b[1])
            längd = botten - topp
            if längd < minst:
                continue
            mitt = (int(xv) + int(xh)) // 2
            inne = hi[topp:botten + 1, mitt]
            # Fyllningen: ljust nerifrån och upp (tomma delen är mörk/genomskinlig).
            # Jämför med rörets mörkaste del (tom), men högst 140: en helt full
            # mätare har ingen mörk del.
            tom = min(140, int(np.percentile(inne, 10)))
            ljus = inne >= max(160, tom + 30, _fyllgräns(inne))
            # Räkna från botten; de nedersta raderna (rörets kant) får vara mörka.
            nerifrån = ljus[::-1]
            start = next((k for k in range(min(8, len(nerifrån))) if nerifrån[k]), None)
            n = 0
            if start is not None:
                n = start
                for v in nerifrån[start:]:
                    if not v:
                        break
                    n += 1
            # Grön topp strax ovanför röret gör det säkert att det är mätaren.
            ovan = bild[max(0, y0 + topp - 20):y0 + topp + 3, x0 + mitt, :3].astype(np.int16)
            grön = bool(((ovan[:, 1] > ovan[:, 2] + 30) & (ovan[:, 1] > ovan[:, 0] + 20)).any())
            poäng = längd + (1000 if grön else 0)
            if bäst is None or poäng > bäst[0]:
                bäst = (poäng, min(1.0, n / längd), x0 + mitt, grön, y0 + topp, y0 + botten)
    if bäst is None or not bäst[3]:
        return None
    return (bäst[1], bäst[2], bäst[4], bäst[5])


def hitta_liten_kastmätare(bild):
    """Kastmätaren när kameran är långt bort (t.ex. i en bil): mätaren krymper
    till ~70 px hög och fyllningen blir ett vitt streck 1-3 px brett, utan de
    mörka kantlinjerna. Letar efter ett smalt vitt lodrätt streck med mätarens
    gröna topp rakt ovanför. Returnerar (andel, x, topp, botten) eller None."""
    import numpy as np
    H, W = bild.shape[:2]
    x0, x1, y0, y1 = int(0.30 * W), int(0.80 * W), int(0.20 * H), int(0.88 * H)
    del_ = bild[y0:y1, x0:x1, :3]
    lo8, hi8 = _lo_hi(del_)
    lo, hi = lo8.astype(np.int16), hi8.astype(np.int16)
    vit = (lo8 >= 150) & (hi8 - lo8 <= 45)
    # Smalt: 4 px åt sidorna är det tydligt mörkare.
    smal = np.zeros_like(vit)
    smal[:, 4:-4] = vit[:, 4:-4] & (hi[:, :-8] < lo[:, 4:-4] - 60) & (hi[:, 8:] < lo[:, 4:-4] - 60)
    minst = max(6, int(0.006 * H))
    kol = np.flatnonzero(smal.sum(axis=0) >= minst)
    bäst = None
    for x in kol:
        rader = np.flatnonzero(smal[:, x])
        run = max(_körningar(rader, 10), key=len)   # ljusa saker bredvid bryter ibland
        if len(run) < minst:
            continue
        yt, yb = int(run[0]), int(run[-1])
        # Grön topp rakt ovanför (högst ~0,15 H upp).
        övre = max(0, yt - int(0.15 * H))
        remsa = del_[övre:yt, max(0, x - 1):x + 2].astype(np.int16)
        if remsa.size == 0:
            continue
        r, g, b = remsa[..., 2], remsa[..., 1], remsa[..., 0]   # BGR
        grön = ((g >= 80) & (g >= r + 20) & (g >= b + 40)).any(axis=1)
        gy = np.flatnonzero(grön)
        if len(gy) == 0:
            continue
        # Den gröna toppen är en liten klick (några px): inte ett långt grönt
        # streck och inte en stor grön yta (t.ex. en lampa).
        gy_n = övre + int(gy[-1])
        höjd = 1
        while höjd < len(gy) and gy[-1 - höjd] == gy[-1] - höjd:
            höjd += 1
        if höjd > max(6, int(0.008 * H)):
            continue
        rad = del_[gy_n, :, :].astype(np.int16)
        def _grön(px):
            return px[1] >= 80 and px[1] >= px[2] + 20 and px[1] >= px[0] + 40
        if any(0 <= x + d < rad.shape[0] and _grön(rad[x + d]) for d in (-5, -6, 5, 6)):
            continue
        topp = gy_n + 2                      # strax under den gröna toppen
        längd = yb - topp
        if not (0.03 * H <= längd <= 0.30 * H) or yt < topp:
            continue
        # Den ofyllda delen av röret är inte vit.
        if vit[topp:yt - 1, x].mean() > 0.3 if yt - 1 > topp else False:
            continue
        andel = min(1.0, (yb - yt + 1) / längd)
        if bäst is None or yb - yt > bäst[4]:
            bäst = (andel, x0 + int(x), y0 + topp, y0 + yb, yb - yt)
    return None if bäst is None else bäst[:4]


def _fyllgräns(kol):
    """Fyllningen är nästan vit (~245). Röret är genomskinligt, så något ljust
    bakom det kan se ljust ut, men dämpat - räkna bara det som är nästan lika
    ljust som fyllningen."""
    import numpy as np
    ref = int(np.percentile(kol, 98)) if len(kol) else 0
    return ref - 40 if ref >= 200 else 0


def följ_kastmätare(bild, x, topp, botten):
    """Läser fyllningen i en mätare vars läge redan är känt (från en tidigare bild
    i samma kast). Söker några pixlar åt sidorna (gubben rör sig lite)."""
    import numpy as np
    H, W = bild.shape[:2]
    if not (0 <= topp < botten < H):
        return None
    längd = botten - topp
    bäst = None
    for dx in range(-8, 9):
        xx = x + dx
        if not 0 <= xx < W:
            continue
        kol = bild[topp:botten + 1, xx, :3].astype(np.int16)
        ljus = (kol.min(axis=1) >= max(160, _fyllgräns(kol.max(axis=1)))) & \
            (kol.max(axis=1) - kol.min(axis=1) <= 70)
        nerifrån = ljus[::-1]
        start = next((k for k in range(min(8, len(nerifrån))) if nerifrån[k]), None)
        n = 0
        if start is not None:
            n = start
            for v in nerifrån[start:]:
                if not v:
                    break
                n += 1
        if bäst is None or n > bäst[0]:
            bäst = (n, xx)
    if bäst is None:
        return None
    # Rimlighet: fyllningen är ett smalt ljust streck, inte en ljus yta.
    n, xx = bäst
    if n > 0:
        sida = bild[botten - max(1, n // 2), max(0, xx - 14), :3].min()
        if sida >= 160 and n > 0.5 * längd:
            return None
    return (min(1.0, n / längd), xx)


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


class Utfall:
    """Avgör från progressbaren när och hur kampen tog slut.

    Fångst: progressen når fullt och nollställs direkt efteråt (0 på en gång;
    en riktig tömning tar sekunder), eller så försvinner minispelet och
    verktygsfältet syns där det var. Piercing kan även fånga fisken mitt i,
    då försvinner minispelet med progressen halvvägs.
    Tappad: progressen rinner ut till noll."""

    def __init__(self):
        self.prog = []          # (tid, andel)
        self.nära = None        # senaste gången progressen var full
        self.låga = 0
        self.mörk_start = None
        self.hög_i_mörkt = False
        self.fall_från = None   # progress precis före ett plötsligt fall till ~0

    def bild(self, nu, läge, prog):
        """Anropas för varje bild. Returnerar 'fångad' när kampen är vunnen."""
        if prog is not None:
            förra = self.prog[-1][1] if self.prog else None
            self.prog.append((nu, prog))
            del self.prog[:-60]
            if prog >= 0.97 and förra is not None and förra >= 0.9:
                self.nära = nu
            # Från en bit upp till ~0 på en bild: nollställning (fångst), inte tömning.
            if prog <= 0.03:
                # Högsta värdet strax innan (en mellanbild kan fångas mitt i fallet).
                strax = [p for t, p in self.prog[:-1] if nu - t <= 0.3]
                if strax and max(strax) >= 0.3 and self.fall_från is None:
                    self.fall_från = max(strax)
            elif prog > 0.1:
                self.fall_från = None
            nyss = self.nära is not None and nu - self.nära < 1.0
            self.låga = self.låga + 1 if nyss and prog <= 0.1 else 0
            if self.låga >= 2:
                return "fångad"
        if läge == "mörk":
            if self.mörk_start is None:
                self.mörk_start, self.hög_i_mörkt = nu, False
            if prog is not None and prog >= 0.5:
                self.hög_i_mörkt = True   # progressen syns kvar: kampen pågår
            if self.efter_full() and nu - self.mörk_start >= 0.4 and not self.hög_i_mörkt:
                return "fångad"
        elif läge is not None:
            self.mörk_start = None
        return None

    def efter_full(self):
        """Blev det mörkt precis efter att progressen var full?"""
        return (self.nära is not None and self.mörk_start is not None
                and self.mörk_start - self.nära < 1.0)

    def slut(self, nu, orsak, sista_läge):
        if self.nära is not None and nu - self.nära < 2.0:
            return "fångad"
        if orsak == "timeout":
            return "fångad" if self.efter_full() and not self.hög_i_mörkt else "tappad"
        if self.fall_från is not None:
            return "fångad"     # Piercing m.m.: progressen nollställdes på en gång
        senaste = [p for t, p in self.prog if nu - t < 2.0][-5:]
        if len(senaste) >= 3:
            return "tappad" if sorted(senaste)[len(senaste) // 2] <= 0.06 else "fångad"
        return "tappad" if sista_läge == "mörk" else "fångad"


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
        self.ram = None         # progressbarens ram (y, vänster, höger), lärs in
        self.ram4 = None        # (topp, botten, vänster, höger) när den setts två gånger lika
        self.ram_kand = None

    def ny_reel(self):
        self.spann = None
        self.aktiv = False
        self.linor = None
        self.fisk = None

    # Progressbarens ram i 1920x1080 (uppmätt i användarens spel). Används tills
    # en egen har hittats; läs_fyllning kontrollerar ändå att ramen syns där.
    STANDARD_RAM = {(1080, 1920): (984, 993, 750, 1169)}

    def läs(self, bild):
        """Returnerar (läge, bar0, bar1, fisk, progress). läge = 'vit', 'mörk' eller None."""
        import numpy as np
        H, W = bild.shape[:2]
        if self.ram4 is None:
            self.ram4 = self.STANDARD_RAM.get((H, W))
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
            prog = läs_fyllning(bild, self.ram4) if self.ram4 else None
            if prog is None:
                geo = {}
                prog = läs_progress(bild, rb, rb - ra, x0, x1, geo=geo)
                if "ram" in geo:
                    self.ram = geo["ram"]
                    kand = (geo["ram"][0], geo["botten"], geo["ram"][1], geo["ram"][2])
                    # Samma ram två gånger i rad = den riktiga (inte en tillfällig felträff).
                    if self.ram_kand and all(abs(a - b) <= 3 for a, b in zip(kand, self.ram_kand)):
                        self.ram4 = kand
                    self.ram_kand = kand
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
        prog = läs_fyllning(bild, self.ram4) if self.ram4 else \
            läs_progress(bild, rb, rb - ra, x0, x1, väntad=self.ram)
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


def hitta_shake(bild, med_radie=False):
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
        # Ringen är vit, eller ljusblå när UI Navigation har markerat knappen.
        lo, hi = _lo_hi(a)
        b, g, r = a[..., 0], a[..., 1], a[..., 2]
        blå = (b >= 200) & (g >= 100) & (b.astype(np.int16) - r >= 90)
        return ((lo >= 155) & (hi - lo <= 40)) | blå

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
            bäst = (täck + p, x0 + xa + fx, y0 + ya + fy, R)
    if bäst is None:
        return None
    return (bäst[1], bäst[2], bäst[3]) if med_radie else (bäst[1], bäst[2])


def _cirkel(ys, xs):
    """Minsta-kvadrat-cirkel genom punkter (Kåsa). Returnerar (cy, cx, R) eller None."""
    import numpy as np
    A = np.column_stack([xs, ys, np.ones(len(xs))])
    b = -(xs ** 2 + ys ** 2)
    try:
        D, E, F = np.linalg.lstsq(A, b, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    cx, cy = -D / 2, -E / 2
    r2 = cx ** 2 + cy ** 2 - F
    return (cy, cx, float(np.sqrt(r2))) if r2 > 0 else None


def snabb_blå_ring(bild):
    """Snabb sökning (några ms) efter en blå, markerad shake-ring.

    De blå pixlarna i shake-området (glest urval) ska ligga på en cirkel av
    rimlig storlek. Det räcker att en del av ringen syns (t.ex. när den delvis
    ligger bakom makrots fönster), men den måste vara rund: en fyrkantig blå
    markering runt en knapp (spelarlistan, kameran) godtas inte.
    Returnerar (x, y, R) i skärmkoordinater."""
    import numpy as np
    H, W = bild.shape[:2]
    s = 3
    x0, y0 = int(SHAKE_OMRÅDE[0] * W), int(SHAKE_OMRÅDE[1] * H)
    x1, y1 = int(SHAKE_OMRÅDE[2] * W), int(SHAKE_OMRÅDE[3] * H)
    reg = bild[y0:y1:s, x0:x1:s]
    b, g, r = reg[..., 0], reg[..., 1], reg[..., 2]
    blå = (b >= 200) & (g >= 100) & (b.astype(np.int16) - r >= 90)
    ys, xs = np.nonzero(blå)
    if len(ys) < 25:
        return None
    # Den största klumpen: pixlar nära medianen (en ring åt gången syns).
    my, mx = np.median(ys), np.median(xs)
    gräns = 0.16 * min(H, W) / s
    nära = (np.abs(ys - my) < gräns) & (np.abs(xs - mx) < gräns)
    ys, xs = ys[nära].astype(float), xs[nära].astype(float)
    if len(ys) < 25:
        return None
    c = _cirkel(ys, xs)
    # Anpassa om på punkterna nära cirkeln (annat blått i närheten stör inte).
    for _ in range(2):
        if c is None:
            return None
        d = np.sqrt((ys - c[0]) ** 2 + (xs - c[1]) ** 2)
        inne = np.abs(d - c[2]) < 0.12 * c[2]
        if inne.sum() < 20:
            return None
        c = _cirkel(ys[inne], xs[inne])
    if c is None:
        return None
    cy, cx, R = c
    if not (0.035 * H <= R * s <= 0.14 * H):
        return None
    d = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
    if (np.abs(d - R) < 0.08 * R).mean() < 0.8:
        return None     # inte rund (t.ex. en fyrkantig markering runt en knapp)
    # Hur mycket av varvet syns? Minst ~40 % (resten kan vara skymt).
    vinkel = ((np.arctan2(ys - cy, xs - cx) + np.pi) / (2 * np.pi) * 24).astype(int) % 24
    if len(np.unique(vinkel)) < 10:
        return None
    return (int(x0 + cx * s), int(y0 + cy * s), float(R * s))


SOBER_GRÅ = (58, 54, 54)   # BGR: Ubuntus ruta "Sober Is Not Responding" (mörkt tema)


def hitta_dialog(bild):
    """Letar efter en dialogruta mitt på skärmen som stoppar spelet: en stor,
    enfärgat grå ruta med skarpa kanter (Ubuntus "Sober svarar inte", Robloxs
    "Disconnected"/"Reconnect" o.s.v.). Returnerar (typ, (x0, y0, x1, y1)) där
    typ är "sober" eller "ruta", annars None. Tar några ms."""
    import numpy as np
    H, W = bild.shape[:2]
    s = 4
    ya, yb, xa, xb = int(0.22 * H), int(0.82 * H), int(0.22 * W), int(0.78 * W)
    reg = bild[ya:yb:s, xa:xb:s, :3].astype(np.int16)
    lo, hi = reg.min(axis=2), reg.max(axis=2)
    grå = (hi - lo <= 10) & (lo >= 20) & (hi <= 110)
    if grå.mean() < 0.1:
        return None
    # Rutans färg = vanligaste gråa färgen; rutan = pixlar nästan exakt den färgen.
    r3 = reg.astype(np.int32) // 3
    kod = r3[..., 0] * 10000 + r3[..., 1] * 100 + r3[..., 2]
    värden, antal = np.unique(kod[grå], return_counts=True)
    k = int(värden[antal.argmax()])
    färg = np.array([k // 10000 * 3 + 1, k // 100 % 100 * 3 + 1, k % 100 * 3 + 1])
    mask = (np.abs(reg - färg).max(axis=2) <= 4)
    ys, xs = np.nonzero(mask)
    if len(ys) < 200:
        return None
    y0, y1 = np.percentile(ys, [3, 97]).astype(int)
    x0, x1 = np.percentile(xs, [3, 97]).astype(int)
    if (x1 - x0) * s < 0.18 * W or (y1 - y0) * s < 0.1 * H:
        return None
    if mask[y0:y1 + 1, x0:x1 + 1].mean() < 0.55:
        return None
    # Skarpa kanter: strax ovanför och under rutan ser det helt annorlunda ut.
    def kantskillnad(rad_in, rad_ut):
        if not (0 <= rad_ut < reg.shape[0]):
            return 1.0
        return (np.abs(reg[rad_ut, x0:x1 + 1] - färg).max(axis=1) > 12).mean()
    if kantskillnad(y0 + 1, y0 - 3) < 0.6 or kantskillnad(y1 - 1, y1 + 3) < 0.6:
        return None
    ruta = (xa + x0 * s, ya + y0 * s, xa + x1 * s, ya + y1 * s)
    typ = "sober" if np.abs(färg - np.array(SOBER_GRÅ)).max() <= 3 else "ruta"
    return typ, ruta


def tumnagel(bild):
    """Glest urval av skärmens mitt (makrots fönster och pekaren påverkar knappt)."""
    import numpy as np
    H, W = bild.shape[:2]
    # ner till reel-spelet: en bar som rör sig räknas också som liv
    return bild[int(0.2 * H):int(0.95 * H):24, int(0.25 * W):int(0.75 * W):24, :3].astype(np.int16)


def har_ändrats(a, b):
    """Skiljer sig två tumnaglar (mer än pekaren/brus)?"""
    import numpy as np
    if a is None or b is None or a.shape != b.shape:
        return True
    return (np.abs(a - b).max(axis=2) > 8).mean() > 0.02


def ring_är_blå(bild, x, y, R):
    """Är shake-ringen blå, dvs. markerad av UI Navigation? Då träffar Enter
    just den knappen (och inte t.ex. dansmenyn eller kameran)."""
    import numpy as np
    H, W = bild.shape[:2]
    v = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    träff = n = 0
    for r in (R * 0.94, R, R * 1.06):
        xs = np.clip((x + r * np.cos(v)).astype(int), 0, W - 1)
        ys = np.clip((y + r * np.sin(v)).astype(int), 0, H - 1)
        px = bild[ys, xs].astype(np.int16)
        träff += int(((px[:, 0] >= 200) & (px[:, 1] >= 100) & (px[:, 0] - px[:, 2] >= 90)).sum())
        n += len(v)
    return träff / n >= 0.25


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


def spara_apng(sökväg, rutor):
    """Animerad PNG. rutor = [(tid_ms, bgr-bild), ...], alla lika stora."""
    import numpy as np
    h, w = rutor[0][1].shape[:2]

    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    def komprimera(bgr):
        rgb = np.ascontiguousarray(bgr[:, :, ::-1]).reshape(h, w * 3)
        upp = np.vstack([rgb[:1], rgb[1:] - rgb[:-1]])          # PNG-filter "Up"
        typ = np.full((h, 1), 2, np.uint8)
        typ[0] = 0
        upp[0] = rgb[0]
        return zlib.compress(np.concatenate([typ, upp], axis=1).tobytes(), 6)

    with open(sökväg + ".tmp", "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"acTL", struct.pack(">II", len(rutor), 0)))
        nr = 0
        for i, (t, bild) in enumerate(rutor):
            fördröjning = (rutor[i + 1][0] - t) if i + 1 < len(rutor) else 1500
            fördröjning = max(10, min(5000, int(fördröjning)))
            f.write(chunk(b"fcTL", struct.pack(">IIIIIHHBB", nr, w, h, 0, 0,
                                               fördröjning, 1000, 0, 0)))
            nr += 1
            data = komprimera(bild)
            if i == 0:
                f.write(chunk(b"IDAT", data))
            else:
                f.write(chunk(b"fdAT", struct.pack(">I", nr) + data))
                nr += 1
        f.write(chunk(b"IEND", b""))
    os.replace(sökväg + ".tmp", sökväg)


# ---------------------------------------------------------------- Fångstloggen

def fångsttext_utsnitt(bild):
    """Området där "You just caught a ... at ...kg! (1/N)" står (full upplösning)."""
    H, W = bild.shape[:2]
    # 20-80 % av bredden: inte makrots eget fönster till vänster.
    return bild[int(0.70 * H):int(0.88 * H), int(0.20 * W):int(0.80 * W), :3].copy()


def _textmask(c, metod=0):
    """Ljus text med mörk kant (så ser Robloxtext ut) -> True där texten är.

    metod 0: ljus pixel nära mörk kant (bäst på mörk/normal bakgrund).
    metod 1: ljus pixel med mörk kant på båda sidor (tunna streck; klarar ljus
             bakgrund bättre, där bakgrunden intill kanten annars räknas som text).
    metod 2: bara ljusa, nästan vita pixlar (vit text utan hänsyn till kanten).
    metod 3: ljusa pixlar nära kanten som skiljer sig tydligt från bakgrundens
             färg (vit och färgad text på ljus/färgad bakgrund)."""
    import numpy as np
    hi = c.max(axis=2)
    if metod == 2:
        return c.min(axis=2) >= 200
    if metod == 3:
        bakgrund = np.median(c.reshape(-1, 3), axis=0)
        skiljer = np.abs(c - bakgrund).max(axis=2) > 90
        mörk = hi <= 90
        nära = mörk.copy()
        for s in (-3, -2, -1, 1, 2, 3):
            nära |= np.roll(mörk, s, 0)
            nära |= np.roll(mörk, s, 1)
        return (hi >= 150) & skiljer & nära
    mörk = hi <= (80 if metod == 0 else 90)
    ljus = hi >= 175
    if metod == 0:
        nära = mörk.copy()
        for s in (-3, -2, -1, 1, 2, 3):
            nära |= np.roll(mörk, s, 0)
            nära |= np.roll(mörk, s, 1)
        return ljus & nära

    def någon(riktning, axel):
        ut = np.zeros_like(mörk)
        for s in range(1, 6):
            ut |= np.roll(mörk, riktning * s, axel)
        return ut
    return ljus & ((någon(1, 1) & någon(-1, 1)) | (någon(1, 0) & någon(-1, 0)))


def ocr_rader(utsnitt, skärmhöjd, max_rader=3, metod=0):
    """Läser de textrader i utsnittet som har mest text (tesseract, en rad åt gången)."""
    import numpy as np
    import tempfile
    t = _textmask(utsnitt.astype(np.int16), metod)
    h = max(8, int(0.018 * skärmhöjd))
    per = t.sum(axis=1)
    kand = sorted(((per[i:i + h].sum(), i) for i in range(0, max(1, len(per) - h), max(2, h // 3))),
                  reverse=True)
    texter, tagna = [], []
    for _, i in kand:
        if len(tagna) >= max_rader:
            break
        if any(abs(i - j) < h for j in tagna):
            continue
        tagna.append(i)
        band = t[max(0, i - 4):i + h + 6]
        kol = np.flatnonzero(band.sum(axis=0) > 0)
        if len(kol) < 10:
            continue
        band = band[:, max(0, kol[0] - 8):kol[-1] + 8]
        # Svart text på vitt i dubbel storlek med mjuka kanter (tesseract läser
        # kantiga, pixliga bokstäver dåligt).
        stor = np.kron(band.astype(np.float32), np.ones((2, 2), np.float32))
        p = np.pad(stor, 1, mode="edge")
        mjuk = sum(p[dy:dy + stor.shape[0], dx:dx + stor.shape[1]]
                   for dy in range(3) for dx in range(3)) / 9
        svv = (255 - mjuk * 255).astype(np.uint8)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fil:
            sökväg = fil.name
        try:
            spara_png(sökväg, np.stack([svv] * 3, axis=2))
            # Lägsta prioritet och en tråd: spelet och makrot går före.
            kommando = ["tesseract", sökväg, "-", "--psm", "7"]
            if shutil.which("nice"):
                kommando = ["nice", "-n", "19"] + kommando
            ut = subprocess.run(kommando, capture_output=True, text=True, timeout=10,
                                env=dict(os.environ, OMP_THREAD_LIMIT="1")).stdout.strip()
            if ut:
                texter.append(ut)
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            try:
                os.remove(sökväg)
            except OSError:
                pass
    return texter


def tolka_fångst(text):
    """"You just caught a Shiny Mullet at 1.4kg! (1/889)" -> dict eller None.

    Tål vanliga läsfel från textläsningen: "caughta", "augnt", "ai"/"al" i
    stället för "at", "ke"/"kg:" i stället för "kg"."""
    import re
    t = re.sub(r"[‘’'`´\"“”¢*_|]", " ", text)
    m = re.search(r"(?:caug\w*|cau\w*|augn\w*|ught\w*)\W+(.+?)\W+"
                  r"(?:at|ai|al|af|ar|av|a1|ot|si)\W*(\d[\d.,]*)\s*([kK]|t\b|[a-z¢!])", t)
    if not m:
        return None
    ord_ = m.group(1).split()
    # "a"/"an" före namnet (ibland feltolkat som "2", "3", "4", "e", "o")
    if len(ord_) > 1 and re.fullmatch(r"(?i)an?|[234eo@]", ord_[0]):
        ord_ = ord_[1:]
    ord_ = re.sub(r"[^A-Za-z -]", "", " ".join(ord_)).split()
    if not ord_ or sum(len(w) for w in ord_) < 3:
        return None
    namn = " ".join(w[:1].upper() + w[1:] if w.islower() and len(w) > 2 else
                    (w[:1].upper() + w[1:].lower() if w.isupper() and len(w) > 2 else w)
                    for w in ord_)
    tal = m.group(2).rstrip(".,")
    # Fisch visar vikten med en decimal och komma som tusentalsavgränsare
    # ("1,105.8kg"). Textläsningen blandar ihop punkt och komma, så: tre siffror
    # efter en avgränsare = tusental, annars decimaler.
    import re as _re
    delar = _re.split(r"[.,]", tal)
    if len(delar) == 1:
        tal = delar[0]
    elif len(delar[-1]) == 3:
        tal = "".join(delar)
    else:
        tal = "".join(delar[:-1]) + "." + delar[-1]
    try:
        kg = float(tal) * (1000 if m.group(3) == "t" and "." in tal else 1)
    except ValueError:
        return None
    c = re.search(r"\(\s*1\s*/\s*(\d[\d,.]*)\s*[)}\]!]", t[m.end():])
    chans = None
    if c:
        try:
            chans = int(c.group(1).replace(",", "").replace(".", ""))
        except ValueError:
            pass
    return {"namn": namn, "kg": round(kg, 2), "chans": chans}


def dela_mutationer(namn, mutationer=MUTATIONER, fiskar=()):
    """"Shiny Sparkling Mullet" -> (["Shiny", "Sparkling"], "Mullet").
    Stannar när resten är en känd fisk ("Big Giant Seadevil" -> Big + Giant Seadevil)."""
    ord_ = namn.split()
    muts = []
    hittat = True
    while hittat and len(ord_) > 1 and " ".join(ord_) not in fiskar:
        hittat = False
        for n in (3, 2, 1):             # även mutationer i flera ord ("Tentacle Surge")
            if len(ord_) > n and " ".join(ord_[:n]) in mutationer:
                muts.append(" ".join(ord_[:n]))
                del ord_[:n]
                hittat = True
                break
    return muts, " ".join(ord_)


def _tolka_prefix(ord_, mutationer):
    """Orden före fisknamnet ska vara mutationer/storlek (läsfel tillåts) eller
    korta skräpbitar. Returnerar (rättade mutationer, poäng) eller (None, None);
    poängen = likhet × antal tecken, för att jämföra olika tolkningar."""
    import difflib
    muts, i, poäng = [], 0, 0.0
    while i < len(ord_):
        for n in (3, 2, 1):
            if i + n > len(ord_):
                continue
            bit = " ".join(ord_[i:i + n])
            t = difflib.get_close_matches(bit, mutationer, 1, 0.6 if len(bit) <= 3 else 0.75)
            if t and len(t[0].split()) == n:
                muts.append(t[0])
                poäng += difflib.SequenceMatcher(None, bit, t[0]).ratio() * len(bit)
                i += n
                break
        else:
            if len(ord_[i]) > 2:
                return None, None       # ett riktigt ord som inte är en mutation
            i += 1                      # skräp som "a" eller "s" före namnet
    return muts, poäng


def rätta_namn(namn, fisknamn, mutationer=MUTATIONER):
    """Rättar läsfel mot prislistans fisknamn och mutationerna:
    "Albitio Sawiish" -> "Albino Sawfish", "Cankiecubier Shark" -> "Cookiecutter Shark".
    Oförändrat om inget fisknamn liknar tillräckligt."""
    import difflib
    ord_ = namn.split()
    if not ord_ or not fisknamn:
        return namn
    bäst = None     # (total likhet, -k, fisk, mutationer)
    for k in range(len(ord_)):
        muts, poäng = _tolka_prefix(ord_[:k], mutationer)
        if muts is None:
            continue
        rest = " ".join(ord_[k:])
        träff = difflib.get_close_matches(rest, fisknamn, 1, 0.75)
        if träff:
            r = difflib.SequenceMatcher(None, rest.lower(), träff[0].lower()).ratio()
            total = (poäng + r * len(rest)) / len(namn)
            if bäst is None or (total, -k) > bäst[:2]:
                bäst = (total, -k, träff[0], muts)
    if bäst is None:
        return namn
    return " ".join(bäst[3] + [bäst[2]])


def läs_fångst(utsnitt_lista, skärmhöjd, kända=(), fisknamn=(), mutationer=MUTATIONER):
    """Läser fångsttexten i flera bilder och väger ihop svaren.

    Alla tolkade rader samlas; liknande namn slås ihop (läsfel som "Crak"/"Crab")
    och rättas mot redan kända namn. Varje fisk som syns i flera bilder loggas
    (vid "Extra!" fångas två fiskar på en gång). Returnerar (lista, råtext)."""
    import collections
    import difflib
    svar, rå = [], []
    for nr, u in enumerate(utsnitt_lista):
        if nr == 1 and not svar and not any(
                "ou" in t.lower() or "aug" in t.lower() or "kg" in t.lower() for t in rå):
            break       # ingen fångsttext alls i första bilden: inget att läsa
        for metod in (0, 3, 1, 2):
            hittat = False
            for rad in ocr_rader(u, skärmhöjd, metod=metod):
                rå.append(rad)
                r = tolka_fångst(rad)
                if r:
                    svar.append(r)
                    hittat = True
            if hittat:
                break
    if not svar:
        return None, rå
    # Gruppera liknande namn.
    grupper = []    # [namn, [svar]]
    for r in svar:
        for g in grupper:
            if difflib.SequenceMatcher(None, r["namn"].lower(), g[0].lower()).ratio() >= 0.75:
                g[1].append(r)
                break
        else:
            grupper.append([r["namn"], [r]])
    minst = 2 if len(utsnitt_lista) >= 2 else 1
    ut = []
    for _, rs in sorted(grupper, key=lambda g: -len(g[1])):
        if len(rs) < minst and ut:
            continue
        if ut:
            # En andra fisk ("Extra!") ska ha annan vikt; samma vikt = samma fisk
            # med ett felläst namn.
            första = ut[0]["kg"]
            kg2 = collections.Counter(r["kg"] for r in rs).most_common(1)[0][0]
            if abs(kg2 - första) <= 0.05 * max(första, 0.1):
                continue
            namn2 = collections.Counter(r["namn"] for r in rs).most_common(1)[0][0]
            if difflib.SequenceMatcher(None, namn2.lower(), ut[0]["namn"].lower()).ratio() >= 0.5:
                continue    # samma fisk, läst fel (t.ex. "Bnentom Key" = "Phantom Ray")
        namn = collections.Counter(r["namn"] for r in rs).most_common(1)[0][0]
        namn = rätta_namn(namn, fisknamn, mutationer)
        if kända:
            nära = difflib.get_close_matches(namn, list(kända), 1, 0.8)
            if nära:
                namn = nära[0]
        kg = collections.Counter(r["kg"] for r in rs).most_common(1)[0][0]
        chanser = [r["chans"] for r in rs if r["chans"]]
        chans = collections.Counter(chanser).most_common(1)[0][0] if chanser else None
        ut.append({"namn": namn, "kg": kg, "chans": chans})
    return ut[:2], rå


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
      film_*.png    - animerad PNG av sista sekunderna i kampen (öppna i Firefox)
      film_*.json   - vad makrot såg och gjorde i varje bild av kampen
    Med en GitHub-token laddas allt upp automatiskt till ett privat repo.
    """

    MAX_BILDER = 300
    MAX_MB = 400          # mappen hålls under så här många MB
    FILM_FPS = 10
    FILM_SEK = 5
    MAX_FILMER = {"tappad": 8, "fångad": 3}    # per pass (filmerna är stora)

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
        self.film = collections.deque(maxlen=self.FILM_FPS * self.FILM_SEK)  # (tid, radnr, bild)
        self.rader = []       # en rad per bild i kampen: [tid, läge, b0, b1, fisk, prog, tryck]
        self.utsnitt = None   # (y0, y1, x0, x1) för filmen
        self.kamp_t0 = 0
        self.förra_bild = None
        self.n_filmer = {"tappad": 0, "fångad": 0}
        self.senaste_film = None
        threading.Thread(target=self._skrivare, daemon=True).start()
        threading.Thread(target=self._uppladdare, daemon=True).start()
        threading.Thread(target=self._hämta_wiki_senare, daemon=True).start()
        threading.Thread(target=self._gamla_skärmbilder, daemon=True).start()

    # ---- insamling (anropas från makrotråden, måste vara snabbt)
    def på(self):
        return bool(self.inst.get("diagnostik"))

    def kast(self, andel):
        if self.på():
            self.rapport["kast"] = (self.rapport["kast"] + [andel])[-500:]

    def kast_mätning(self, fördröjning, spår, t_släpp):
        """Uppmätt tid från släpp tills kastmätaren stannade, med mätarens värden."""
        if self.på():
            rad = {"fördröjning": fördröjning,
                   "spår": [[round(t - t_släpp, 3), None if v is None else round(v, 2)]
                            for t, v in spår]}
            self.rapport["kastfördröjning"] = (self.rapport.get("kastfördröjning", []) + [rad])[-100:]

    def kamp_start(self):
        if self.på():
            self.kamp = {"start": round(time.time(), 1), "bilder": 0, "vit": 0, "mörk": 0,
                         "borta": 0, "fisk_i_bar": 0, "fisk_sedd": 0, "prog_max": 0.0}
            self.buffert.clear()
            self.film.clear()
            self.rader = []
            self.utsnitt = None
            self.kamp_t0 = time.time()

    def kamp_bild(self, bild, läge, b0, b1, fisk, prog, band=None):
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
        if len(self.rader) < 20000:
            self.rader.append([round(nu - self.kamp_t0, 3), läge,
                               None if b0 is None else int(b0), None if b1 is None else int(b1),
                               None if fisk is None else int(fisk),
                               None if prog is None else round(float(prog), 3), 0])
        ny = bild is not None and bild is not self.förra_bild
        self.förra_bild = bild
        if ny and (not self.buffert or nu - self.buffert[-1][0] > 0.25):
            self.buffert.append((nu, bild))
        if ny and band and (not self.film or nu - self.film[-1][0] >= 1 / self.FILM_FPS - 0.005):
            self._filmbild(nu, bild, band)

    def _filmbild(self, nu, bild, band):
        """Sparar reel-området i halv upplösning (medel av 2x2, så tunna streck syns kvar)."""
        import numpy as np
        H, W = bild.shape[:2]
        if self.utsnitt is None:
            # Baren, progressbaren och överkanten av verktygsfältet.
            y0, y1 = int(0.80 * H), int(0.97 * H)
            x0, x1 = int(REEL_OMRÅDE[0] * W), int(REEL_OMRÅDE[2] * W)
            self.utsnitt = tuple(int(v) for v in (y0, y0 + (y1 - y0) // 2 * 2,
                                                   x0, x0 + (x1 - x0) // 2 * 2))
        y0, y1, x0, x1 = self.utsnitt
        u = bild[y0:y1, x0:x1, :3]
        if u.shape[0] != y1 - y0 or u.shape[1] != x1 - x0:
            return
        u = u.astype(np.uint16)
        halv = ((u[0::2, 0::2] + u[1::2, 0::2] + u[0::2, 1::2] + u[1::2, 1::2]) >> 2).astype(np.uint8)
        self.film.append((nu, len(self.rader) - 1, halv))

    def kamp_tryck(self, håll):
        """Vad makrot bestämde sig för på senaste bilden (håll inne eller släpp)."""
        if self.kamp and self.rader:
            self.rader[-1][6] = 1 if håll else 0

    def kamp_slut(self, resultat, kamptid, orsak=None, styrning=None):
        k, self.kamp = self.kamp, None
        if not (self.på() and k):
            return
        k["resultat"] = resultat
        k["tid"] = round(kamptid, 1)
        k["orsak"] = orsak              # full progress / borta / timeout
        k["styrning"] = styrning        # inlärd fysik: [upp, ner, fördröjning]
        k["bilder_per_s"] = round(k["bilder"] / kamptid, 1) if kamptid > 0 else None
        # Hur nära fisken baren låg (px från barens mitt), när båda syntes.
        avst = [abs((r[2] + r[3]) / 2 - r[4]) for r in self.rader
                if r[1] == "vit" and r[2] is not None and r[4] is not None]
        if avst:
            avst.sort()
            k["avstånd_median"] = round(avst[len(avst) // 2])
            k["avstånd_p95"] = round(avst[int(len(avst) * 0.95)])
        self.rapport["kamper"] = (self.rapport["kamper"] + [k])[-500:]
        if resultat in self.n_filmer and len(self.film) >= 5 \
                and self.n_filmer[resultat] < self.MAX_FILMER[resultat]:
            self.n_filmer[resultat] += 1
            namn = f"film_{'fangad' if resultat == 'fångad' else 'tappad'}_{time.strftime('%H%M%S')}"
            self.skrivkö.put(("film", namn, list(self.film), self.rader, self.utsnitt, k,
                             self.kamp_t0))
        self.film.clear()
        self.rader = []
        self.förra_bild = None
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
        if self.på() and bild is not None and self.n_fångstbilder < 10:
            self.n_fångstbilder += 1
            self.bild(f"fangst_{time.strftime('%H%M%S')}", bild, halv=True)

    def shake(self, tid, stat):
        """Hur shake-fasen gick: tid från kast till minispel, Enter/klick, ringar."""
        if self.på():
            self.rapport.setdefault("shake", [])
            self.rapport["shake"] = (self.rapport["shake"] + [dict(stat, tid=tid)])[-300:]

    def rättning(self, resultat):
        """Fångsttexten syntes efter en kamp som räknats som tappad."""
        if self.på() and resultat == "tappad":
            r = self.rapport["resultat"]
            r["tappad"] = max(0, r.get("tappad", 0) - 1)
            r["fångad"] = r.get("fångad", 0) + 1
            self.rapport["rättade"] = self.rapport.get("rättade", 0) + 1

    def fångsttext(self, utsnitt, rå, tolkat):
        """Fångsttexten i full upplösning + vad textläsningen fick fram (för finjustering)."""
        if not self.på():
            return
        self.rapport.setdefault("fångsttext", [])
        self.rapport["fångsttext"] = (self.rapport["fångsttext"] +
                                      [[time.strftime("%H:%M:%S"), rå, tolkat]])[-200:]
        if utsnitt is not None and getattr(self, "n_texter", 0) < 40:
            self.n_texter = getattr(self, "n_texter", 0) + 1
            self.bild(f"fangsttext_{time.strftime('%H%M%S')}", utsnitt)

    # Färdigritade sidor (action=render ger HTML med de mallgenererade tabellerna).
    WIKI_SIDOR = ("All_Fish", "Mutations", "Template:Fish_Table", "Template:Mutation_Table")

    def _gamla_skärmbilder(self):
        """F8-bilder från äldre versioner låg i autoclicker-mappen: flytta dem till
        diagnostik/skarmbilder och ladda upp dem."""
        import glob
        import shutil as sh
        time.sleep(10)
        if not self.på():
            return
        mapp = os.path.join(MAPP, "diagnostik", "skarmbilder")
        for gammal in sorted(glob.glob(os.path.join(MAPP, "fisch_bild_*.png")))[-60:]:
            try:
                os.makedirs(mapp, exist_ok=True)
                datum = time.strftime("%Y%m%d", time.localtime(os.path.getmtime(gammal)))
                ny = os.path.join(mapp, os.path.basename(gammal).replace(
                    "fisch_bild_", f"fisch_bild_{datum}_"))
                sh.move(gammal, ny)
                self.uppkö.put(ny)
            except OSError:
                pass

    def _hämta_wiki_senare(self):
        time.sleep(20)
        try:
            self.hämta_wiki()
        except Exception as fel:
            self.logg(f"Diagnostik: wikisidorna kunde inte hämtas ({fel})")

    def hämta_wiki(self):
        """Laddar ner Fisch-wikins fisk- och mutationssidor en gång och lägger dem i
        diagnostiken, så att prislistan (grundpris per kg, mutationer) kan byggas."""
        import urllib.request
        if not self.på() or self.inst.get("wiki_hämtad2") or not self.inst.get("gh_token"):
            return
        mapp = os.path.join(MAPP, "diagnostik", "wiki")
        os.makedirs(mapp, exist_ok=True)
        antal = 0
        for sida in self.WIKI_SIDOR:
            for typ, url in (("wikitext", f"https://fischipedia.org/index.php?title={sida}&action=raw"),
                             ("html", f"https://fischipedia.org/index.php?title={sida}&action=render")):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FischMakro"})
                    with urllib.request.urlopen(req, timeout=20) as svar:
                        data = svar.read()
                except Exception as fel:
                    data = f"FEL: {fel!r}".encode()
                sökväg = os.path.join(mapp, f"{sida.replace(':', '_')}.{typ}.txt")
                with open(sökväg, "wb") as fil:
                    fil.write(data[:8_000_000])
                self.uppkö.put(sökväg)
                antal += len(data) > 1000
        if antal:
            self.inst["wiki_hämtad2"] = True
            self.logg(f"Diagnostik: laddade ner {antal} wikisidor till prislistan")

    def kastfilm(self, rutor):
        """Kort film (full upplösning) runt gubben under kastet, när kastmätaren
        inte hittades, så att mätarens utseende och fyllning syns (högst 3 per pass)."""
        if self.på() and len(rutor) >= 3 and getattr(self, "n_kastfilmer", 0) < 3:
            self.n_kastfilmer = getattr(self, "n_kastfilmer", 0) + 1
            self.skrivkö.put(("kastfilm", f"kastfilm_{time.strftime('%H%M%S')}", rutor))

    def kastbild(self, bild):
        """En bild mitt i kastet när kastmätaren inte hittades (högst 3 per pass)."""
        if self.på() and bild is not None and getattr(self, "n_kastbilder", 0) < 3:
            self.n_kastbilder = getattr(self, "n_kastbilder", 0) + 1
            self.bild(f"kast_{time.strftime('%H%M%S')}", bild, halv=True)

    def shakebild(self, bild):
        """En bild när ingen shake-knapp har synts på 3 s (högst 5 per pass)."""
        if self.på() and bild is not None and getattr(self, "n_shakebilder", 0) < 5:
            self.n_shakebilder = getattr(self, "n_shakebilder", 0) + 1
            self.bild(f"shake_{time.strftime('%H%M%S')}", bild, halv=True)

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
                elif jobb[0] == "kastfilm":
                    _, namn, rutor = jobb
                    t0 = rutor[0][0]
                    sökväg = os.path.join(self.mapp, namn + ".png")
                    spara_apng(sökväg, [(round((t - t0) * 1000), b) for t, b in rutor])
                    self.uppkö.put(sökväg)
                    self._städa()
                elif jobb[0] == "film":
                    for sökväg in self._spara_film(*jobb[1:]):
                        self.uppkö.put(sökväg)
                    self._städa()
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

    def _spara_film(self, namn, bilder, rader, utsnitt, kamp, kamp_t0):
        """Skriver filmen som animerad PNG (spelas i webbläsare) plus data för varje bild.

        Överst i varje filmbild finns en remsa med vad makrot såg:
        vit/orange linje = baren (vit/mörk), röd = fisken, cyan = progress,
        grön ruta vänster = håller inne musknappen, grå = släppt."""
        import numpy as np
        y0, y1, x0, x1 = utsnitt
        t0 = bilder[0][0]
        rutor = []
        for t, i, halv in bilder:
            r = rader[i] if 0 <= i < len(rader) else [0, None, None, None, None, None, 0]
            _, läge, b0, b1, fisk, prog, tryck = r
            h, w = halv.shape[:2]
            remsa = np.zeros((12, w, 3), np.uint8)
            if b0 is not None and b1 is not None:
                a, b = max(0, (b0 - x0) // 2), min(w, (b1 - x0) // 2 + 1)
                remsa[2:6, a:b] = (255, 255, 255) if läge == "vit" else (0, 140, 255)
            if fisk is not None and 0 <= (fisk - x0) // 2 < w:
                fx = (fisk - x0) // 2
                remsa[0:10, max(0, fx - 1):fx + 2] = (0, 0, 255)
            if prog is not None:
                remsa[8:10, :int(w * min(1.0, max(0.0, prog)))] = (255, 255, 0)
            remsa[0:12, 0:12] = (0, 200, 0) if tryck else (90, 90, 90)
            rutor.append((round((t - t0) * 1000), np.concatenate([remsa, halv])))
        mapp = self.mapp
        png = os.path.join(mapp, namn + ".png")
        spara_apng(png, rutor)
        data = os.path.join(mapp, namn + ".json")
        with open(data, "w", encoding="utf-8") as fil:
            json.dump({"version": VERSION, "kamp": kamp,
                       "utsnitt_y0_y1_x0_x1": list(utsnitt), "skala": 0.5, "remsa_px": 12,
                       "kolumner": ["tid", "läge", "bar0", "bar1", "fisk", "progress", "tryck"],
                       "rader": rader,
                       "filmbilder_tid_rad": [[round(t - kamp_t0, 3), i] for t, i, _ in bilder]},
                      fil, ensure_ascii=False, separators=(",", ":"))
        self.senaste_film = png
        return [data, png]

    def _städa(self):
        """Tar bort de äldsta filerna när mappen blir för stor (rapporterna sparas)."""
        bas = os.path.join(MAPP, "diagnostik")
        filer = []
        for rot, _, namn in os.walk(bas):
            if os.path.basename(rot) == "skarmbilder":
                continue        # användarens egna F8-bilder tas inte bort
            filer += [os.path.join(rot, f) for f in namn if f.endswith((".png", ".json"))
                      and f != "rapport.json"]
        try:
            filer = sorted(((os.path.getmtime(f), os.path.getsize(f), f) for f in filer))
        except OSError:
            return
        storlek = sum(s for _, s, _ in filer)
        antal = len(filer)
        for _, s, f in filer:
            if antal <= self.MAX_BILDER and storlek <= self.MAX_MB * 1e6:
                break
            try:
                os.remove(f)
            except OSError:
                pass
            antal -= 1
            storlek -= s

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
        urllib.request.urlopen(req, timeout=180).close()


# ---------------------------------------------------------------- Makrot

class Blockerad(Exception):
    """En dialogruta (Sober svarar inte, utkastad ...) ligger över spelet."""

    def __init__(self, dialog):
        super().__init__(dialog[0])
        self.dialog = dialog


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
        # Progressbarens ram (sitter alltid på samma ställe; sparas till nästa gång,
        # så att den kan läsas även där den är svår att hitta, t.ex. på ljus sand).
        sparad_ram = inst.get("progressram")
        if isinstance(sparad_ram, list) and len(sparad_ram) == 4:
            self.syn.ram4 = tuple(int(v) for v in sparad_ram)
        # Spelets fysik (lärs in under fisket och sparas till nästa gång).
        sparad = inst.get("styrning")
        try:
            self.styrning = Styrning(*[float(x) for x in sparad][:2], L=float(sparad[2]))
        except (TypeError, ValueError, IndexError):
            self.styrning = Styrning(L=0.3)
        # Tiden från släpp tills kastmätaren stannar på skärmen (mäts vid varje kast).
        try:
            self.kast_ledtid = min(0.45, max(0.05, float(inst["kast_ledtid"])))
        except (KeyError, TypeError, ValueError):
            self.kast_ledtid = None
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
            mapp = os.path.join(MAPP, "diagnostik", "skarmbilder")
            os.makedirs(mapp, exist_ok=True)
            sökväg = os.path.join(mapp, time.strftime("fisch_bild_%Y%m%d_%H%M%S.png"))
            spara_png(sökväg, bild)
            self.diag.uppkö.put(sökväg)   # laddas upp med diagnostiken
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

    def vakt(self, bild):
        """Kollar (högst ~2 ggr/s) om en dialogruta ligger över spelet.
        Syns den två gånger i rad avbryts det makrot håller på med (Blockerad),
        så att det inte trycker Enter i rutan (i Sober-rutan är Force Quit förvald)."""
        nu = time.time()
        if bild is None or nu - getattr(self, "senast_vakt", 0) < 0.4:
            return
        self.senast_vakt = nu
        # Frusen skärm: bilden står helt still (spelet har hängt sig).
        tn = tumnagel(bild)
        if har_ändrats(tn, getattr(self, "vakt_tumnagel", None)):
            self.vakt_tumnagel, self.senast_ändring = tn, nu
        elif nu - getattr(self, "senast_ändring", nu) > 20:
            self.senast_ändring = nu
            raise Blockerad(("fryst", None))
        d = hitta_dialog(bild)
        if d is None:
            self.dialog_sedd = 0
            return
        self.dialog_sedd = getattr(self, "dialog_sedd", 0) + 1
        if self.dialog_sedd >= 2:
            self.dialog_sedd = 0
            raise Blockerad(d)

    def hantera_blockering(self, dialog):
        """Pausar tills rutan är borta. Sober-rutan: klicka Vänta (inte Force Quit)."""
        self.inp.release_all()
        typ = dialog[0]
        bild = self.skärm.hämta()
        self.diag.fel(f"dialogruta: {typ}", bild)
        if typ == "sober":
            text = "Sober svarar inte. Makrot klickar på Vänta och fortsätter när spelet svarar igen."
            self.status("Sober svarar inte – väntar")
        elif typ == "fryst":
            text = ("Spelet verkar ha frusit (bilden har stått helt still i 20 s). Makrot "
                    "väntar tills spelet rör sig igen (och försöker igen efter en stund).")
            self.status("Spelet har frusit – väntar")
        else:
            text = ("En ruta ligger över spelet (utkastad?). Makrot pausar och fortsätter "
                    "själv när rutan är borta.")
            self.status("Ruta över spelet – pausar")
        senast = getattr(self, "senast_larm", {}).get(typ, 0)
        if time.time() - senast > 600:
            self.q.put(("larm", text))
            self.senast_larm = dict(getattr(self, "senast_larm", {}), **{typ: time.time()})
        else:
            self.logg(text)
        klickat = larmat = 0.0
        start = time.time()
        borta = 0
        fryst_tn = tumnagel(bild) if bild is not None else None
        while True:
            self.vänta(0.5)
            bild = self.skärm.hämta()
            d = hitta_dialog(bild) if bild is not None else None
            if typ == "fryst" and d is None:
                # Klart när bilden har börjat röra sig igen.
                ok = bild is not None and har_ändrats(tumnagel(bild), fryst_tn)
                if ok:
                    borta += 1
                    fryst_tn = tumnagel(bild)
                    if borta >= 3:
                        break
                else:
                    borta = 0
                nu = time.time()
                if nu - start > 45:
                    break       # försök fiska igen (om spelet bara var ovanligt stilla)
                if nu - start > 60 and nu - larmat > 600:
                    larmat = nu
                    self.q.put(("larm", f"Spelet har stått still i {int((nu - start) / 60)} min – "
                                        "kolla datorn (starta om Sober?)."))
                continue
            if d is None:
                borta += 1
                if borta >= 3:
                    break
                continue
            borta = 0
            nu = time.time()
            if d[0] == "sober" and nu - klickat > 8:
                # Knappen "Vänta" (Wait) sitter till höger längst ner i rutan.
                x0, y0, x1, y1 = d[1]
                H, W = bild.shape[:2]
                self.inp.flytta((x0 + 0.745 * (x1 - x0)) / W, (y0 + 0.815 * (y1 - y0)) / H)
                self.pekare_flyttad = True
                time.sleep(0.05)
                self.inp.tap(BTN_LEFT)
                klickat = nu
                self.logg("Klickade på Vänta i rutan \"Sober svarar inte\"")
            if nu - start > 60 and nu - larmat > 600:
                larmat = nu
                self.q.put(("larm", f"Rutan ligger kvar efter {int((nu - start) / 60)} min – "
                                    "kolla datorn."))
        self.senast_ändring = time.time()
        self.logg(f"Spelet syns igen efter {time.time() - start:.0f} s – fortsätter fiska")
        self.q.put(("larm_slut", None))

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
        kastbild = False
        filmrutor = []       # (tid, utsnitt runt gubben) för diagnostiken
        förra = None
        först_sett = None
        högst = 0.0
        känd = None
        förslag = None       # möjlig mätare som ännu inte har setts växa
        while True:
            nu = time.time()
            if nu - start > 3.0 or (not sett and nu - start > max(1.2, self.inst["cast_tid"])):
                self.diag.kastfilm(filmrutor)
                return sett and self.släpp("maxtid")
            if sett and nu - först_sett > 1.2 and högst < 0.15:
                # Mätaren "syns" men rör sig inte: fel träff, släpp som vanligt.
                self.diag.kastfilm(filmrutor)
                return self.släpp("mätaren rör sig inte")
            self.vänta(0)
            bild = self.skärm.hämta()
            self.vakt(bild)
            m = hitta_kastmätare(bild) if bild is not None else None
            if m is not None and not sett:
                # Mätaren börjar tom och växer. Något stillastående med grön topp
                # (text, kanten på en sak) är inte mätaren: kräv att den har vuxit.
                samma = förslag is not None and abs(m[1] - förslag[1]) <= 4 and \
                    abs(m[2] - förslag[2]) <= 6
                if not (samma and m[0] >= förslag[0] + 0.03):
                    if not samma or m[0] < förslag[0]:
                        förslag = m
                    m = None
            if m is not None and sett and abs(m[1] - känd[0]) > 20:
                m = None            # något annat än mätaren vi följer
            if m is not None:
                känd = (m[1], m[2], m[3])
            elif sett and bild is not None:
                m = följ_kastmätare(bild, *känd)   # samma mätare, sökningen missade
            if bild is not None and bild is not förra and len(filmrutor) < 40 and self.diag.på():
                H, W = bild.shape[:2]
                filmrutor.append((nu, bild[int(0.45 * H):int(0.80 * H),
                                            int(0.35 * W):int(0.60 * W)].copy()))
            förra = bild
            if m is None:
                if not sett and not kastbild and nu - start > 0.5:
                    kastbild = True
                    self.diag.kastbild(bild)
                time.sleep(0.005)
                continue
            if not sett:
                först_sett = nu
            sett = True
            andel = m[0]
            högst = max(högst, andel)
            prover.append((time.time(), andel))
            prover = prover[-5:]
            fart = hastighet(prover)
            # Mätaren pendlar (upp ~1/s, ner igen) och det tar en stund innan
            # släppet märks i spelet. Släpp därför INNAN toppen, så att spelet
            # får släppet precis när mätaren är högst. Fördröjningen mäts efter
            # varje kast (se mät_kastfördröjning); tills dess gissas den utifrån
            # styrningens inlärda fördröjning. Missas toppen får man vänta ett
            # helt varv (~2 s), så släpp också om den redan har vänt högt upp.
            ledtid = self.kast_ledtid if self.kast_ledtid is not None else \
                min(0.35, max(0.08, self.styrning.L)) + 0.05
            fart = min(fart, 1.6)      # det första hoppet ger ofta en för hög fart
            säker = len(prover) >= 3 and andel >= 0.5 and fart > 0.3
            kvar = (1.0 - andel) / fart - ledtid if säker else 9.9   # s tills släpp
            mellan = (prover[-1][0] - prover[0][0]) / (len(prover) - 1) if len(prover) > 1 else 0.1
            if (säker and kvar <= min(0.12, mellan)) or \
                    (andel >= 0.85 and fart <= 0.0) or andel >= 0.99:
                if säker and kvar > 0:
                    time.sleep(kvar)    # nästa bild kommer för sent: vänta ut exakt tid
                andel_släpp = andel + max(0.0, kvar) * fart if säker else andel
                self.släpp(f"{andel_släpp:.0%}")
                if känd is not None:
                    self.mät_kastfördröjning(känd, filmrutor)
                self.diag.kastfilm(filmrutor)   # de första kasten per pass, för kontroll
                return True
            time.sleep(0.003)

    def mät_kastfördröjning(self, känd, filmrutor):
        """Tittar på mätaren en kort stund efter släppet: den rör sig tills spelet
        har fått släppet och stannar eller försvinner sedan. Tiden dit är hela
        fördröjningen (skärmbild + tangent), vilken styr hur tidigt nästa kast
        ska släppas."""
        t_släpp = time.time()
        förra = None
        spår = []          # (tid, andel eller None)
        while time.time() - t_släpp < 0.6:
            bild = self.skärm.hämta()
            if bild is None or bild is förra:
                time.sleep(0.004)
                continue
            förra = bild
            nu = time.time()
            m = följ_kastmätare(bild, *känd)
            spår.append((nu, None if m is None else m[0]))
            if self.diag.på() and len(filmrutor) < 48:
                H, W = bild.shape[:2]
                filmrutor.append((nu, bild[int(0.45 * H):int(0.80 * H),
                                            int(0.35 * W):int(0.60 * W)].copy()))
            if len(spår) >= 2 and all(v is None or v < 0.1 for _, v in spår[-2:]):
                break          # borta två bilder i rad
            if len(spår) >= 3 and _kastplatå(spår) is not None and nu - spår[_kastplatå(spår)][0] >= 0.08:
                break          # stilla en stund
        # Första bilden där mätaren har försvunnit eller stannat. (Släpps kastet
        # bara >= 50 %, så en mätare nära 0 är en mätare som har försvunnit.)
        mätt = None
        förr_t = t_släpp
        platå = _kastplatå(spår)
        for i, (t, v) in enumerate(spår):
            if v is None or v < 0.1 or i == platå:
                mätt = (förr_t + t) / 2 - t_släpp
                break
            förr_t = t
        if mätt is None or not spår or not (0.03 <= mätt <= 0.55):
            self.diag.kast_mätning(None, spår, t_släpp)
            return
        gammal = self.kast_ledtid
        self.kast_ledtid = mätt if gammal is None else 0.6 * gammal + 0.4 * mätt
        self.kast_ledtid = min(0.45, max(0.05, self.kast_ledtid))
        self.diag.kast_mätning(round(mätt, 3), spår, t_släpp)

    def släpp(self, orsak):
        self.inp.up(BTN_LEFT)
        self.kast_andel = orsak
        self.diag.kast(float(orsak.rstrip("%")) / 100 if orsak.endswith("%") else orsak)
        return True

    def vänta_på_napp(self, nav_redan_på=False):
        """Väntar tills minispelet dyker upp och sköter shake. False = inget napp.

        UI Navigation: Enter trycks BARA när shake-knappen syns och är markerad
        (blå ring). Blint Enter-tryckande öppnade dansmenyn och kameran när
        något annat råkade vara markerat. Syns knappen men är vit (inte
        markerad) klickas den med musen i stället."""
        läge = self.inst["shake"]
        self.status("Väntar på napp")
        if läge == "navigation" and not nav_redan_på:
            self.nav()
        start = kast_slut = time.time()
        senast_klick = 0.0
        kandidat = None
        träffar = 0
        stat = {"enter": 0, "klick": 0, "ringar": 0, "blå": 0}
        tryckt_på = None     # (x, y) för ringen som Enter senast trycktes på
        varv = 0
        senast_blå = senast_full = 0.0
        senast_ring = time.time()
        senast_navfix = 0.0
        bild_sparad = False
        try:
            while True:
                bild = self.skärm.hämta()
                self.vakt(bild)
                # Två bilder i rad, så att en meny som blinkar förbi inte räknas.
                träffar = träffar + 1 if bild is not None and hitta_reel(bild) else 0
                if träffar >= 2:
                    self.diag.shake(round(time.time() - kast_slut, 2), stat)
                    return True
                if träffar:
                    continue        # minispelet syns nog redan: tryck inget, kolla nästa bild
                nu = time.time()
                if nu - start > self.inst["napp_timeout"]:
                    self.diag.shake(None, stat)
                    return False
                if läge in ("navigation", "klick") and bild is not None:
                    varv += 1
                    H, W = bild.shape[:2]
                    ring = snabb_blå_ring(bild) if läge == "navigation" else None
                    blå = ring is not None
                    if ring is not None:
                        senast_blå = nu
                        if senast_navfix:
                            self.navfix_hjälper = True
                    elif senast_navfix and nu - senast_navfix > 2.0 and \
                            getattr(self, "navfix_hjälper", None) is None:
                        self.navfix_hjälper = False    # blev aldrig blå: försök inte igen
                    # Den långsamma sökningen (vita ringar) bara i klickläge, eller när
                    # ingen blå ring har synts på en stund - och högst en gång per sekund.
                    full_sökning = ring is None and (
                        läge == "klick" or (nu - senast_blå > 1.5 and nu - senast_full > 1.0))
                    if full_sökning:
                        senast_full = nu
                    if full_sökning:
                        ring = hitta_shake(bild, med_radie=True)   # långsam: vita ringar
                        if ring and ring[2] < 0.035 * H:
                            ring = None     # för liten för en shake-knapp (t.ex. en ikon)
                        blå = ring is not None and läge == "navigation" and ring_är_blå(bild, *ring)
                        if ring and not blå and läge == "navigation" and not senast_navfix \
                                and getattr(self, "navfix_hjälper", True):
                            # Vit ring fast UI Navigation borde vara på: den var nog redan
                            # på (och slogs av av oss). Slå på den igen, så blir ringen blå.
                            senast_navfix = nu
                            stat["navfix"] = stat.get("navfix", 0) + 1
                            self.nav()
                            self.vänta(0.1)
                            continue
                    if ring:
                        senast_ring = nu
                    elif not bild_sparad and nu - senast_ring > 3.0:
                        bild_sparad = True      # ingen ring på 3 s: spara en bild
                        self.diag.shakebild(bild)
                    if ring:
                        stat["ringar"] += 1
                        stat["blå"] += blå
                        # Samma ring som nyss trycktes (den tonar bort)? Då kan markeringen
                        # redan ha flyttat till något annat - vänta på nästa ring.
                        samma = tryckt_på is not None and nu - senast_klick < 0.6 and \
                            abs(ring[0] - tryckt_på[0]) < 30 and abs(ring[1] - tryckt_på[1]) < 30
                        if blå and samma:
                            time.sleep(0.01)
                            continue
                        if blå:
                            if nu - senast_klick > self.slump(0.1, 0.3):
                                tryckt_på = ring[:2]
                                self.status("Skakar")
                                self.inp.tap(KEY_ENTER)
                                senast_klick = nu
                                self.shakes += 1
                                stat["enter"] += 1
                                start = nu          # shake = något händer, nollställ timeout
                                kandidat = None
                                self.vänta(0.05)
                            continue
                        # Kräv samma träff i två bilder i rad, så att inget ryck ger felklick.
                        if kandidat and abs(ring[0] - kandidat[0]) < W * 0.02 \
                                and abs(ring[1] - kandidat[1]) < H * 0.02:
                            if nu - senast_klick > self.slump(0.15, 0.3):
                                j = 4 if self.inst["slumpa"] else 0
                                self.status("Skakar")
                                self.inp.flytta((ring[0] + random.uniform(-j, j)) / W,
                                                (ring[1] + random.uniform(-j, j)) / H)
                                self.pekare_flyttad = True
                                time.sleep(0.03)
                                self.inp.tap(BTN_LEFT)
                                senast_klick = nu
                                self.shakes += 1
                                stat["klick"] += 1
                                start = nu
                                kandidat = None
                                self.vänta(0.05)
                                continue
                    if full_sökning or blå:
                        kandidat = ring
                self.vänta(0.03)
        finally:
            if läge == "navigation":
                self.nav()

    def cykel(self):
        """En hel fiskerunda. Returnerar 'fångad', 'tappad' eller 'inget napp'."""
        self.shakes = 0
        self.kamptid = 0.0
        redan = getattr(self, "redan_kastat", False)
        if redan:
            # Shake-knappen syntes redan (blå = UI Navigation är redan på) efter
            # förra fångsten: spelet har redan kastat. Ett nytt tryck skulle bara
            # klicka bort tid.
            self.redan_kastat = False
            self.diag.kast("redan kastat")
        else:
            self.kasta()
            self.vänta(self.slump(0.6))
        if not self.vänta_på_napp(nav_redan_på=redan):
            self.diag.inget_napp(self.skärm.hämta())
            return "inget napp"
        self.status("Drar in")
        kampstart = time.time()
        self.diag.kamp_start()
        resultat = self.reel()
        self.kamptid = time.time() - kampstart
        if self.syn.ram4 and list(self.syn.ram4) != self.inst.get("progressram"):
            self.inst["progressram"] = [int(v) for v in self.syn.ram4]
        st = self.styrning
        self.diag.kamp_slut(resultat, self.kamptid, getattr(self, "kamp_orsak", None),
                            [round(st.upp), round(st.ner), round(st.L, 3)])
        self.vy = None
        # Fångsttexten ("You just caught a ... (1/N)") syns ett par sekunder efter
        # en fångst: ta tre bilder och läs dem i bakgrunden. Det görs efter varje
        # kamp - syns texten efter en "tappad" var den i själva verket fångad.
        utsnitt, bild, ringar = [], None, []
        for paus in (0.4, 0.5, 0.5):
            self.vänta(paus)
            bild = self.skärm.hämta()
            if bild is not None:
                utsnitt.append(fångsttext_utsnitt(bild))
                ringar.append(snabb_blå_ring(bild))
        # Syns shake-knappen redan (på samma ställe i de två sista bilderna) har
        # spelet redan kastat: hoppa över nästa kast.
        if len(ringar) >= 2 and ringar[-1] and ringar[-2] and \
                abs(ringar[-1][0] - ringar[-2][0]) < 20 and abs(ringar[-1][1] - ringar[-2][1]) < 20:
            self.redan_kastat = True
        if resultat == "fångad":
            self.diag.fångstbild(bild)
        if utsnitt and shutil.which("tesseract"):
            threading.Thread(target=self._läs_fångst, args=(utsnitt, bild.shape[0], resultat),
                             daemon=True).start()
        self.vänta(self.slump(0.1, 0.5))
        return resultat

    def _läs_fångst(self, utsnitt, H, resultat="fångad"):
        try:
            r, rå = läs_fångst(utsnitt, H, getattr(self, "kända_namn", ()),
                               getattr(self, "fisknamn", ()),
                               getattr(self, "mutationsnamn", MUTATIONER))
        except Exception as fel:
            r, rå = None, [f"fel: {fel!r}"]
        self.diag.fångsttext(utsnitt[0], rå, r)
        if not r and any("caught" in t.lower() for t in rå):
            r = [{"namn": None}]    # texten syntes men gick inte att tolka: ändå en fångst
        if r:
            self.diag.rättning(resultat)
        self.q.put(("fångst", (r, resultat)))

    def reel(self):
        syn = self.syn
        syn.ny_reel()
        self.styrning.ny_kamp()
        förra_bild, förra_tid = None, 0.0
        start_mitt = None
        rörd = False         # baren står helt still de första ~2 s av kampen
        prover = []          # (tid, bar_mitt) för barens hastighet
        fprover = []         # (tid, fisk_x) för fiskens hastighet
        håll = False
        fisk_rel = 0.5       # var i baren fisken sågs senast (0 = vänster, 1 = höger)
        senast_mitt = None
        borta_sedan = None
        mörk_sedan = None
        utfall = Utfall()
        sista_läge = None
        start = time.time()

        def resultat_av(orsak):
            self.kamp_orsak = orsak
            return utfall.slut(time.time(), orsak, sista_läge)

        try:
            while True:
                self.vänta(0)
                nu = time.time()
                if nu - start > 120:
                    return resultat_av("timeout")
                bild = self.skärm.hämta()
                if bild is None:
                    continue
                if bild is förra_bild and nu - förra_tid < 0.25:
                    time.sleep(0.003)   # ingen ny bild än: samma bild igen ger bara brus
                    continue
                förra_bild, förra_tid = bild, nu
                self.vakt(bild)
                läge, b0, b1, fisk, prog = syn.läs(bild)
                W = bild.shape[1]
                self.diag.kamp_bild(bild, läge, b0, b1, fisk, prog, syn.band)
                if utfall.bild(nu, läge, prog):
                    self.kamp_orsak = "full progress"
                    return "fångad"

                if läge is None:
                    self.inp.up(BTN_LEFT)
                    self.styrning.skickat(nu, False)
                    # Försvann minispelet för att en ruta lade sig över? Då är
                    # kampen varken fångad eller tappad.
                    d = hitta_dialog(bild)
                    if d:
                        raise Blockerad(d)
                    borta_sedan = borta_sedan or nu
                    if nu - borta_sedan > 0.35:
                        return resultat_av("borta")
                    time.sleep(0.01)
                    continue
                borta_sedan = None
                sista_läge = läge

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
                    if start_mitt is None:
                        start_mitt = mitt
                    rörd = rörd or abs(mitt - start_mitt) > 3
                    lo, hi = -1e9, 1e9
                    if syn.spann:   # spårets ändar: baren kan inte åka längre
                        x0 = int(REEL_OMRÅDE[0] * W)
                        kant = 0.02 * (syn.spann[1] - syn.spann[0])   # pilarna i ändarna
                        lo = x0 + syn.spann[0] + kant + (b1 - b0) / 2
                        hi = x0 + syn.spann[1] - kant - (b1 - b0) / 2
                        if hi <= lo:
                            lo, hi = -1e9, 1e9
                    if not rörd:
                        # Spelet håller baren still i början; tryck inte i onödan.
                        håll = fisk > mitt + (b1 - b0) * 0.25
                    else:
                        håll = self.styrning.beslut(nu, mitt, hastighet(prover[-5:]), fisk,
                                                    hastighet(fprover), lo, hi)
                        self.styrning.anpassa(nu)
                elif fisk is not None and senast_mitt is not None:
                    håll = fisk > senast_mitt      # ser fisken men inte baren
                else:
                    håll = fisk_rel > 0.5          # ser inte fisken: jaga åt senaste hållet
                self.styrning.skickat(nu, håll)
                self.diag.kamp_tryck(håll)
                if håll:
                    self.inp.down(BTN_LEFT)
                else:
                    self.inp.up(BTN_LEFT)
                time.sleep(0.005)
        finally:
            self.inp.up(BTN_LEFT)

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
                # Flera kast i rad utan napp: något är troligen fel (meny öppen,
                # UI dolt, utkastad ...). Säg till en gång; fortsätt ändå försöka.
                self.inget_i_rad = getattr(self, "inget_i_rad", 0) + 1 \
                    if resultat == "inget napp" else 0
                if self.inget_i_rad == 3:
                    self.q.put(("larm", "3 kast i rad utan napp – kolla spelet (meny öppen, "
                                        "UI dolt eller utkastad?). Makrot fortsätter försöka."))
            except InterruptedError:
                pass
            except Blockerad as b:
                try:
                    self.hantera_blockering(b.dialog)
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


class Styrning:
    """Förutsägande styrning (MPC) för reel-baren.

    Spelet svarar först efter en fördröjning (L, ~0,25 s i Sober med skärm-
    inspelning), så baren fortsätter i gammal riktning en stund efter varje
    klick. Varje bild: räkna fram var baren är när det nya kommandot börjar
    verka (med de kommandon som redan är på väg), pröva sedan planer av typen
    "håll/släpp i d sekunder, sedan tvärtom" och välj den som håller baren
    närmast fisken. Fysiken (acceleration när man håller/släpper, broms,
    fördröjning) utgår från uppmätta värden och finjusteras medan man fiskar.
    """

    DT = 0.02
    HORISONT = 0.8
    PLANER = (0.04, 0.08, 0.12, 0.18, 0.26, 0.36, 0.5, 0.8)

    def __init__(self, upp=1600.0, ner=600.0, broms=0.5, L=0.2):
        self.upp, self.ner, self.broms, self.L = upp, ner, broms, L
        self.kommandon = []     # (tid, håll) som skickats
        self.historik = []      # (tid, mitt) som setts
        self.senast_anpassad = 0.0

    def ny_kamp(self):
        self.kommandon = []
        self.historik = []

    def _gäller(self, s):
        """Vilket kommando spelet följer vid tiden s (det som skickades före s - L)."""
        h = False
        for tk, hk in self.kommandon:
            if tk <= s - self.L:
                h = hk
            else:
                break
        return h

    def _steg(self, p, v, h, lo, hi, dt):
        v += ((self.upp if h else -self.ner) - self.broms * v) * dt
        p += v * dt
        if p < lo:
            p, v = lo, max(0.0, v)
        elif p > hi:
            p, v = hi, min(0.0, v)
        return p, v

    def beslut(self, nu, mitt, v, fisk, fv, lo=-1e9, hi=1e9):
        """True = håll inne musknappen."""
        self.historik.append((nu, mitt))
        del self.historik[:-80]
        dt = self.DT
        # 1) Fram till att det nya kommandot verkar: följ det som redan är skickat.
        p, vv, s = mitt, v, nu
        while s < nu + self.L - 1e-9:
            p, vv = self._steg(p, vv, self._gäller(s), lo, hi, dt)
            s += dt
        # Fisken: fortsätter en bit åt samma håll, men vänder ofta (dämpad).
        def fisk_vid(tid):
            return fisk + fv * min(tid - nu, 0.3)
        # 2) Pröva planer.
        bäst = {}
        for först in (True, False):
            for d in self.PLANER:
                pp, pv, tt, kost = p, vv, s, 0.0
                while tt < s + self.HORISONT:
                    h = först if tt - s < d else not först
                    pp, pv = self._steg(pp, pv, h, lo, hi, dt)
                    tt += dt
                    kost += (pp - fisk_vid(tt)) ** 2
                if först not in bäst or kost < bäst[först]:
                    bäst[först] = kost
        return bäst[True] < bäst[False]

    def skickat(self, nu, håll):
        """Kommer ihåg vad som skickades (behövs för att förutsäga fördröjningen)."""
        self.kommandon.append((nu, håll))
        if len(self.kommandon) > 200:
            del self.kommandon[:100]

    def anpassa(self, nu):
        """Finjusterar fysiken mot det som setts, en sak i taget (fördröjning,
        acceleration när man håller, acceleration när man släpper)."""
        if nu - self.senast_anpassad < 1.0 or len(self.historik) < 30:
            return
        self.senast_anpassad = nu
        hist = self.historik[-60:]
        self.varv = (getattr(self, "varv", -1) + 1) % 3
        namn = ("L", "upp", "ner")[self.varv]
        nu_värde = getattr(self, namn)
        steg = (-0.1, -0.05, 0.05, 0.1) if namn == "L" else (0.8, 0.9, 1.1, 1.25)
        gränser = {"L": (0.02, 0.45), "upp": (300.0, 8000.0), "ner": (150.0, 6000.0)}[namn]
        bäst = (self._prediktionsfel(hist), nu_värde)
        for st in steg:
            värde = nu_värde + st if namn == "L" else nu_värde * st
            if not gränser[0] <= värde <= gränser[1]:
                continue
            setattr(self, namn, värde)
            fel = self._prediktionsfel(hist)
            if fel < bäst[0] * 0.97:
                bäst = (fel, värde)
        setattr(self, namn, bäst[1])

    def _prediktionsfel(self, hist):
        """Hur väl modellen förutsäger baren 0,4 s framåt från olika startpunkter."""
        fel, n = 0.0, 0
        for i in range(3, len(hist) - 4, 5):
            t0 = hist[i][0]
            v0 = hastighet(hist[i - 3:i + 1])
            p, v, s = hist[i][1], v0, t0
            j = i
            while j + 1 < len(hist) and hist[j + 1][0] - t0 <= 0.4:
                j += 1
                while s < hist[j][0]:
                    p, v = self._steg(p, v, self._gäller(s), -1e9, 1e9, 0.02)
                    s += 0.02
                fel += (p - hist[j][1]) ** 2
                n += 1
        return fel / max(1, n)


def _kastplatå(spår):
    """Index för första bilden varefter kastmätaren står still (±0,02) i minst
    0,06 s, eller None. Enstaka bilder ligger för tätt för att jämföras två och två."""
    for i, (t, v) in enumerate(spår):
        if v is None or v < 0.1:
            return None
        senare = [(u, w) for u, w in spår[i + 1:] if u - t <= 0.12]
        if senare and senare[-1][0] - t >= 0.06 and \
                all(w is not None and abs(w - v) < 0.02 for _, w in senare):
            return i
    return None


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
        self.fisklogg = []   # fångstloggen: {namn, kg, chans, tid}
        try:
            with open(FÅNGST_FIL) as f:
                self.fisklogg = [x for x in json.load(f) if isinstance(x, dict) and x.get("namn")]
        except (OSError, ValueError):
            pass
        self.priser = {}
        try:
            with open(PRISER_FIL) as f:
                self.priser = json.load(f)
        except (OSError, ValueError):
            pass

        self.q = queue.Queue()
        self.makro = Makro(self.inst, self.q)
        self.makro.kända_namn = {x["namn"] for x in self.fisklogg}
        self.namnlistor()
        self.stat = {"fångad": 0, "tappad": 0, "inget napp": 0}
        self.fångster = []   # tidpunkter för fångster (för grafen)
        self.start_tid = None
        self.körtid = 0.0
        self.redo = False

        self.root = root = tk.Tk()
        root.title(f"Fisch Makro v{VERSION}")
        root.configure(bg=BG)
        self.bredd = 360
        root.geometry("360x720")
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
        self.kompakt_knapp = ttk.Button(topp, text="Litet fönster", style="Liten.TButton",
                                        command=self.växla_kompakt)
        self.kompakt_knapp.grid(row=0, column=3, sticky="ne", padx=(6, 0))
        # I litet läge: en rad med det viktigaste.
        self.kompakt_lbl = ttk.Label(topp, text="", style="Panel.TLabel", font=("", 11, "bold"))
        self.kompakt_lbl.grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.kompakt_lbl.grid_remove()
        topp.columnconfigure(1, weight=1)
        self.startknapp = ttk.Button(yttre, text="Starta  (F6)", style="Start.TButton",
                                     command=self.växla, state="disabled")
        self.startknapp.pack(fill="x", pady=(8, 8))
        self.kompakt = False

        self.flikar = flikar = ttk.Notebook(yttre)
        flikar.pack(fill="both", expand=True)
        fiske = ttk.Frame(flikar, padding=(0, 8))
        inst = ttk.Frame(flikar, padding=(0, 8))
        loggflik = ttk.Frame(flikar, padding=(0, 8))
        tavla = ttk.Frame(flikar, padding=(0, 8))
        fångstflik = ttk.Frame(flikar, padding=(0, 8))
        flikar.add(fiske, text="Fiske")
        flikar.add(tavla, text="Statistik")
        flikar.add(fångstflik, text="Fångster")
        flikar.add(inst, text="Inställn.")
        flikar.add(loggflik, text="Logg")

        self.bygg_fiske(fiske)
        self.bygg_inställningar(inst)
        self.bygg_tavla(tavla)
        self.bygg_fångster(fångstflik)
        root.geometry(f"{self.bredd}x720")
        self.logg = tk.Text(loggflik, bg=PANEL, fg=TEXT, relief="flat", wrap="word",
                            font=("monospace", 9), state="disabled", highlightthickness=0)
        self.logg.pack(fill="both", expand=True)

        root.protocol("WM_DELETE_WINDOW", self.stäng)
        self.sätt_status("Startar...", DÄMPAD, "Väntar på lösenord och skärmdelning")
        threading.Thread(target=self.starta_tjänster, daemon=True).start()
        threading.Thread(target=self.makro.loop, daemon=True).start()
        self.root.after(3000, lambda: self.sök_uppdatering(tyst=True))
        threading.Thread(target=self.hämta_priser, daemon=True).start()
        if self.inst.get("kompakt"):
            self.root.after(200, self.växla_kompakt)
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
        stil.configure("Liten.TButton", font=("", 8), padding=(6, 2))
        stil.configure("Val.TRadiobutton", background=PANEL, foreground=DÄMPAD, padding=(6, 4),
                       indicatorsize=0)
        stil.map("Val.TRadiobutton", background=[("selected", "#2b2c40"), ("active", PANEL)],
                 foreground=[("selected", TEXT)])
        stil.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                       rowheight=20, borderwidth=0, font=("", 9))
        stil.configure("Treeview.Heading", background=BG, foreground=DÄMPAD, borderwidth=0,
                       font=("", 8, "bold"))
        stil.map("Treeview", background=[("selected", "#2b2c40")])
        stil.configure("Vertical.TScrollbar", background=PANEL, troughcolor=BG, bordercolor=BG,
                       arrowcolor=DÄMPAD, lightcolor=PANEL, darkcolor=PANEL)
        stil.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BG,
                       lightcolor=BG, darkcolor=BG, tabmargins=0)
        stil.configure("TNotebook.Tab", background=BG, foreground=DÄMPAD, padding=(4, 4),
                       font=("", 8),
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

    # ---- fångstloggen
    def bygg_fångster(self, f):
        tk, ttk = self.tk, self.ttk
        val = ttk.Frame(f, style="Panel.TFrame")
        val.pack(fill="x")
        self.fångst_läge = tk.StringVar(value="sällsynt")
        for värde, text in (("sällsynt", "Sällsyntast"), ("tyngst", "Tyngst"),
                            ("värde", "Mest värd")):
            ttk.Radiobutton(val, text=text, value=värde, variable=self.fångst_läge,
                            style="Val.TRadiobutton", command=self.rita_fångster
                            ).pack(side="left", expand=True, fill="x")
        sökrad = ttk.Frame(f)
        sökrad.pack(fill="x", pady=(6, 4))
        ttk.Label(sökrad, text="Sök:").pack(side="left", padx=(0, 6))
        self.fångst_sök = tk.StringVar()
        ttk.Entry(sökrad, textvariable=self.fångst_sök).pack(side="left", fill="x", expand=True)
        self.fångst_sök.trace_add("write", lambda *_a: self.rita_fångster())
        ram = ttk.Frame(f)
        ram.pack(fill="both", expand=True)
        # Bredder och radhöjd efter typsnittets verkliga storlek (Ubuntu kan skala upp
        # texten, då klipptes kolumnerna och raderna överlappade).
        import tkinter.font as tkfont
        typs = tkfont.Font(font=self.ttk.Style().lookup("Treeview", "font") or "TkDefaultFont")
        self.ttk.Style().configure("Treeview", rowheight=typs.metrics("linespace") + 6)
        mät = typs.measure
        kol = (("nr", "#", mät("100") + 8, "e"), ("fisk", "Fisk", mät("Grandpa Horse") + 6, "w"),
               ("kg", "kg", mät("1 105.8") + 10, "e"), ("chans", "1 på", mät("10 000") + 10, "e"),
               ("värde", "C$", mät("99 999") + 10, "e"))
        # Fönstret måste vara minst så brett (tabell + rullist + marginaler).
        self.bredd = max(360, sum(k[2] for k in kol) + mät("Grandpa") + 50)
        self.fångst_träd = träd = ttk.Treeview(ram, columns=[k[0] for k in kol], show="headings")
        for namn, rubrik, bredd, just in kol:
            träd.heading(namn, text=rubrik)
            träd.column(namn, width=bredd, minwidth=20, anchor=just, stretch=(namn == "fisk"))
        rull = ttk.Scrollbar(ram, orient="vertical", command=träd.yview)
        träd.configure(yscrollcommand=rull.set)
        träd.pack(side="left", fill="both", expand=True)
        rull.pack(side="right", fill="y")
        self.fångst_info = ttk.Label(f, text="", style="Dämpad.TLabel", wraplength=300)
        self.fångst_info.pack(fill="x", pady=(6, 0))
        self.rita_fångster()

    def namnlistor(self):
        """Ger textläsningen prislistans fisk- och mutationsnamn (för att rätta
        läsfel) och rättar redan loggade namn som lästes fel."""
        fiskar = list(self.priser.get("fiskar", {}))
        if not fiskar:
            return
        self.makro.fisknamn = fiskar
        self.makro.mutationsnamn = self.mutationslista()
        ändrat = False
        for x in self.fisklogg:
            nytt = rätta_namn(x["namn"], fiskar, self.makro.mutationsnamn)
            if nytt != x["namn"]:
                x["namn"], ändrat = nytt, True
        if ändrat:
            self.spara_fisklogg()
        self.makro.kända_namn = {x["namn"] for x in self.fisklogg}

    def mutationslista(self):
        return MUTATIONER + [m for m in self.priser.get("mutationer", {}) if m not in MUTATIONER]

    def värde(self, x):
        """Grundpris per kg × vikt × mutationernas multiplikatorer (None om priset saknas)."""
        muts, fisk = dela_mutationer(x["namn"], self.mutationslista(),
                                     self.priser.get("fiskar", {}))
        info = self.priser.get("fiskar", {}).get(fisk)
        if not info or not info.get("kg_pris"):
            return None
        mult = 1.0
        for m in muts:
            mult *= float(self.priser.get("mutationer", {}).get(m, 1.0))
        return float(info["kg_pris"]) * float(x["kg"]) * mult

    def rita_fångster(self):
        if not hasattr(self, "fångst_träd"):
            return
        lista = self.fisklogg
        sök = self.fångst_sök.get().strip().lower()
        if sök:
            lista = [x for x in lista if sök in x["namn"].lower()]
        läge = self.fångst_läge.get()
        if läge == "sällsynt":
            lista = sorted(lista, key=lambda x: x.get("chans") or 0, reverse=True)
        elif läge == "tyngst":
            lista = sorted(lista, key=lambda x: x.get("kg") or 0, reverse=True)
        else:
            lista = sorted((x for x in lista if self.värde(x) is not None),
                           key=self.värde, reverse=True)
        träd = self.fångst_träd
        träd.delete(*träd.get_children())
        for i, x in enumerate(lista[:100], 1):
            kg = x.get("kg") or 0
            vikt = f"{kg:,.1f}".replace(",", " ") if kg >= 1000 else f"{kg:g}"
            chans = f"{x['chans']:,}".replace(",", " ") if x.get("chans") else "–"
            v = self.värde(x)
            träd.insert("", "end", values=(i, x["namn"], vikt, chans,
                                           f"{v:,.0f}".replace(",", " ") if v is not None else "–"))
        info = f"{len(self.fisklogg)} fångster loggade. Topp 100 visas."
        if läge == "värde" and not self.priser.get("fiskar"):
            info += (" Värde kräver prislistan (grundpris per kg och mutationer); den laddas "
                     "ner automatiskt så fort den finns.")
        if not shutil.which("tesseract"):
            info += " Textläsning saknas: starta om appen så installeras den."
        self.fångst_info.config(text=info)

    def spara_fisklogg(self):
        try:
            os.makedirs(os.path.dirname(FÅNGST_FIL), exist_ok=True)
            with open(FÅNGST_FIL + ".tmp", "w", encoding="utf-8") as f:
                json.dump(self.fisklogg, f, ensure_ascii=False)
            os.replace(FÅNGST_FIL + ".tmp", FÅNGST_FIL)
        except OSError:
            pass

    def hämta_priser(self):
        """Laddar ner prislistan (grundpris per kg, mutationer) om den finns."""
        import urllib.request
        try:
            req = urllib.request.Request(PRISER_URL + f"?t={int(time.time())}",
                                         headers={"User-Agent": "FischMakro"})
            with urllib.request.urlopen(req, timeout=15) as svar:
                data = json.loads(svar.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("fiskar"):
                os.makedirs(os.path.dirname(PRISER_FIL), exist_ok=True)
                with open(PRISER_FIL, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                self.q.put(("priser", data))
        except Exception:
            pass

    # ---- litet fönster
    def växla_kompakt(self):
        self.kompakt = not self.kompakt
        if self.kompakt:
            self.flikar.pack_forget()
            self.startknapp.pack_forget()
            self.kompakt_lbl.grid()
            self.kompakt_knapp.config(text="Stort fönster")
            self.root.minsize(240, 80)
            self.root.geometry(f"{self.bredd}x130")
        else:
            self.kompakt_lbl.grid_remove()
            self.startknapp.pack(fill="x", pady=(8, 8))
            self.flikar.pack(fill="both", expand=True)
            self.kompakt_knapp.config(text="Litet fönster")
            self.root.minsize(300, 560)
            self.root.geometry(f"{self.bredd}x720")
        if bool(self.inst.get("kompakt")) != self.kompakt:
            self.inst["kompakt"] = self.kompakt
            self.spara_konfig()

    def spara_hist(self):
        try:
            os.makedirs(os.path.dirname(STAT_FIL), exist_ok=True)
            with open(STAT_FIL, "w") as f:
                json.dump(self.hist, f, indent=1, ensure_ascii=False)
        except OSError:
            pass

    def rätta_till_fångad(self):
        """Senaste "tappad" var egentligen en fångst (fångsttexten syntes)."""
        if self.stat["tappad"] > 0:
            self.stat["tappad"] -= 1
        self.stat["fångad"] += 1
        self.fångster.append(time.time())
        tot = self.hist["totalt"]
        tot["tappad"] = max(0, tot.get("tappad", 0) - 1)
        tot["fångad"] = tot.get("fångad", 0) + 1
        dagar = self.hist.setdefault("dagar", {})
        dag = time.strftime("%Y-%m-%d")
        dagar[dag] = dagar.get(dag, 0) + 1
        if self.session:
            self.session["tappad"] = max(0, self.session.get("tappad", 0) - 1)
            self.session["fångad"] = self.session.get("fångad", 0) + 1
        self.spara_hist()
        self.skriv("   ↺ Rättat: fångad (fångsttexten syntes)")

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
        # Smalt nog för fönstret (~32 tecken): start, längd (h:mm), fiskar, per timme, träff.
        rader = [f"{'Start':<12}{'Tid':>5}{'Fisk':>5}{'/h':>5}{'Träff':>6}"]
        for p in reversed(self.hist["sessioner"][-15:]):
            pt = p.get("tid", 0)
            pf, ptp = p.get("fångad", 0), p.get("tappad", 0)
            rader.append(f"{time.strftime('%d/%m %H:%M', time.localtime(p['start'])):<12}"
                         f"{int(pt // 3600)}:{int(pt % 3600 // 60):02d}".rjust(5) +
                         f"{pf:>5}{(pf / pt * 3600 if pt else 0):>5.0f}"
                         f"{(f'{100 * pf / (pf + ptp):.0f}%' if pf + ptp else '–'):>6}")
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
        ttk.Button(dg, text="Visa senaste film", command=self.visa_film
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

    def visa_film(self):
        """Öppnar senaste filmen i webbläsaren (bildvisare spelar inte alltid animerad PNG)."""
        import glob
        import shutil
        filmer = glob.glob(os.path.join(MAPP, "diagnostik", "*", "film_*.png"))
        if not filmer:
            self.skriv("Inga filmer än. En film sparas när en fisk tappas.")
            return
        film = max(filmer, key=os.path.getmtime)
        for prog in ("firefox", "google-chrome", "chromium", "chromium-browser", "xdg-open"):
            if shutil.which(prog):
                try:
                    subprocess.Popen([prog, film])
                    return
                except OSError:
                    pass
        self.skriv(f"Filmen ligger i {film}")

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
        if self.kompakt:
            takt = f"{f / tid * 3600:.0f}/h" if tid > 60 else "–/h"
            self.kompakt_lbl.config(text=f"🐟 {f}   ✗ {t}   {takt}   {h}:{rest // 60:02d}")
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
                    st = self.makro.styrning
                    self.inst["styrning"] = [round(st.upp), round(st.ner), round(st.L, 3)]
                    if self.makro.kast_ledtid is not None:
                        self.inst["kast_ledtid"] = round(self.makro.kast_ledtid, 3)
                    if sum(self.stat.values()) % 5 == 0:
                        self.spara_konfig()
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
                elif typ == "larm":
                    self.skriv("⚠ " + data)
                    self.sätt_status("Pausad", GUL, data)
                    if self.inst["notiser"]:
                        notis(data)
                    self.discord("⚠ Fisch Makro: " + data)
                elif typ == "fångst":
                    fiskar, gissat = data
                    # Samma fisk (namn + vikt) nyss? Texten kan synas kvar efter nästa kamp.
                    nu_t = time.time()
                    senaste = getattr(self, "senaste_fiskar", [])
                    senaste = [(t, n, k) for t, n, k in senaste if nu_t - t < 20]
                    if fiskar and fiskar[0].get("namn") and any(
                            n == fiskar[0]["namn"] and abs(k - fiskar[0]["kg"]) < 0.5
                            for _, n, k in senaste):
                        fiskar = None
                    for x in fiskar or []:
                        if x.get("namn"):
                            senaste.append((nu_t, x["namn"], x["kg"]))
                    self.senaste_fiskar = senaste
                    if fiskar and gissat == "tappad":
                        # Fångsttexten syntes: det var en fångst, inte en förlust.
                        self.rätta_till_fångad()
                    for data in [x for x in (fiskar or []) if x.get("namn")]:
                        data = dict(data, tid=time.strftime("%Y-%m-%d %H:%M"))
                        self.fisklogg.append(data)
                        self.spara_fisklogg()
                        self.makro.kända_namn = {x["namn"] for x in self.fisklogg}
                        chans = f"  (1 på {data['chans']:,})".replace(",", " ") \
                            if data.get("chans") else ""
                        self.skriv(f"   {data['namn']}, {data['kg']:g} kg{chans}")
                        self.rita_fångster()
                elif typ == "priser":
                    self.priser = data
                    self.namnlistor()
                    self.rita_fångster()
                elif typ == "larm_slut":
                    self.skriv("✓ Spelet syns igen – fiskar vidare")
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


def saknade_paket_ocr():
    return [] if shutil.which("tesseract") else ["tesseract"]


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
    # Bara en app åt gången: två makron som styr musen samtidigt ger kaos.
    import fcntl
    os.makedirs(os.path.dirname(KONFIG), exist_ok=True)
    global _LÅS
    _LÅS = open(os.path.join(os.path.dirname(KONFIG), "app.lock"), "w")
    try:
        fcntl.flock(_LÅS, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            import tkinter as tk
            from tkinter import messagebox
            rot = tk.Tk()
            rot.withdraw()
            messagebox.showinfo("Fisch Makro", "Fisch Makro körs redan (kolla fönstren).\n"
                                "Två makron samtidigt styr musen om varandra.")
        except Exception:
            print("Fisch Makro körs redan.")
        sys.exit(0)
    markering = os.path.join(os.path.dirname(KONFIG), "ocr_forsokt")
    if saknade_paket_ocr() and not os.path.exists(markering):
        # Textläsningen (fångstloggen) är inte nödvändig: ett försök, sedan kör appen
        # ändå (och frågar inte igen varje start).
        print("Installerar textläsning (tesseract) för fångstloggen...")
        subprocess.run(root_kommando(["apt-get", "install", "-y", "tesseract-ocr"]), check=False)
        try:
            os.makedirs(os.path.dirname(markering), exist_ok=True)
            open(markering, "w").close()
        except OSError:
            pass
    try:
        # Lägre prioritet än spelet: Sober får datorkraften först (när datorn var
        # hårt belastad hängde Sober sig: "Sober Is Not Responding").
        os.nice(5)
    except OSError:
        pass
    App().kör()


if __name__ == "__main__":
    main()
