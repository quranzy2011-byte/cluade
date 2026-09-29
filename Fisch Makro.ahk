#Requires AutoHotkey v2.0
#SingleInstance Force
; Fisch Makro - startare for Windows.
; Dubbelklicka pa den har filen. Forsta gangen installeras det som behovs
; (Python, numpy, mss) och makrot laddas ner. Sedan startar makrot direkt.
; F6 = starta/stoppa, F8 = skarmbild, Esc = stoppa (styrs av makrot sjalvt).

URL := "https://raw.githubusercontent.com/quranzy2011-byte/cluade/main/fisch_app.py"
mapp := EnvGet("USERPROFILE") "\FischMakro"
app := mapp "\fisch_app.py"
DirCreate(mapp)

py := HittaPython()
if (py = "") {
    svar := MsgBox("Python behovs for Fisch Makro men hittades inte.`n`nInstallera Python nu? (tar ett par minuter)", "Fisch Makro", "YesNo Icon?")
    if (svar = "No")
        ExitApp
    try {
        RunWait('winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements')
    } catch {
        MsgBox("Kunde inte installera automatiskt. Ladda ner Python fran python.org (bocka i 'Add python.exe to PATH') och dubbelklicka pa den har filen igen.", "Fisch Makro")
        Run("https://www.python.org/downloads/windows/")
        ExitApp
    }
    py := HittaPython()
    if (py = "") {
        MsgBox("Python installerades men hittas inte an. Starta om datorn eller dubbelklicka pa filen igen.", "Fisch Makro")
        ExitApp
    }
}

if !FileExist(app) {
    try {
        Download(URL, app)
    } catch {
        MsgBox("Kunde inte ladda ner makrot. Kolla internet och forsok igen.", "Fisch Makro")
        ExitApp
    }
}

; numpy och mss (skarmbilder) - installeras en gang.
konsol := StrReplace(py, "pythonw.exe", "python.exe")
if RunWait('"' konsol '" -c "import numpy, mss, tkinter"', mapp, "Hide") != 0 {
    RunWait('"' konsol '" -m pip install --user --upgrade numpy mss', mapp)
}

; Textlasning (fangstloggen) - valfritt, fragar en gang.
markering := mapp "\ocr_fragat"
if !FileExist(markering) && !FileExist(EnvGet("ProgramFiles") "\Tesseract-OCR\tesseract.exe") {
    FileAppend("", markering)
    if (MsgBox("Vill du installera textlasning (Tesseract)?`nDen behovs bara for fangstloggen (vilka fiskar du fangat). Fisket fungerar utan.", "Fisch Makro", "YesNo Icon?") = "Yes") {
        try RunWait('winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements')
    }
}

Run('"' py '" "' app '"', mapp)
ExitApp

HittaPython() {
    lokal := EnvGet("LOCALAPPDATA") "\Programs\Python"
    prog := EnvGet("ProgramFiles")
    for ver in ["313", "312", "311", "310"] {
        for bas in [lokal "\Python" ver, prog "\Python" ver] {
            if FileExist(bas "\pythonw.exe")
                return bas "\pythonw.exe"
        }
    }
    ; Via "py"-startaren (python.org)
    tmp := A_Temp "\fisch_py.txt"
    try {
        RunWait(A_ComSpec ' /c py -3 -c "import sys;print(sys.executable)" > "' tmp '"', , "Hide")
        sokvag := Trim(FileRead(tmp), " `r`n")
        FileDelete(tmp)
        if InStr(sokvag, "python.exe") && !InStr(sokvag, "WindowsApps") {
            w := StrReplace(sokvag, "python.exe", "pythonw.exe")
            if FileExist(w)
                return w
        }
    }
    return ""
}
