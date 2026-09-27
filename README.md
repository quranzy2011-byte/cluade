# Fisch Makro

Fiskemakro för Roblox-spelet Fisch på Ubuntu (Wayland) med Sober.

- `fisch_app.py` – appen (sidopanel med live-vy, statistik och inställningar).
  Appen söker själv efter nya versioner härifrån: Inställningar → Uppdatering.
- `installera_ikon.sh` – lägger till "Fisch Makro" i appmenyn.

Installera:

```
mkdir -p ~/autoclicker && cd ~/autoclicker
curl -fsSLO https://raw.githubusercontent.com/quranzy2011-byte/cluade/main/fisch_app.py
curl -fsSLO https://raw.githubusercontent.com/quranzy2011-byte/cluade/main/installera_ikon.sh
sh installera_ikon.sh
```

F6 start/stopp, F8 skärmbild, Esc stopp.
