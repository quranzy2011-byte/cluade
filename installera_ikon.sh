#!/bin/sh
# Lägger till "Fisch Makro" i Ubuntus appmeny (öppnar appen med sidopanel).
MAPP="$HOME/autoclicker"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/fisch-makro.desktop" <<SLUT
[Desktop Entry]
Type=Application
Name=Fisch Makro
Comment=Fiskar automatiskt i Fisch
Exec=python3 "$MAPP/fisch_app.py"
Path=$MAPP
Icon=applications-games
Terminal=false
Categories=Game;
SLUT
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null
echo "Klart! Tryck på Windows-tangenten och skriv 'Fisch'."
