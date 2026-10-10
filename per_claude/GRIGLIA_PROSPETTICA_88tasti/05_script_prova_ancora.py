"""
Misura di ancoraggio su un frame, con una QUALSIASI versione di `griglia_prospettica.py`:
inlier dell'affinamento, quanti tasti restano inquadrati e che estensione in x coprono le
celle (serve a vedere se la griglia copre tutta la tastiera o solo una meta').

E' l'arnese usato per le prove A/B fra le versioni del modulo: per esempio il file qui
accanto `01_codice_griglia_prospettica_NUOVO.py` contro `02_codice_griglia_prospettica_PRIMA.py`.

Uso:
  python3 05_script_prova_ancora.py <modulo_griglia.py> [video] [frame]
Default: video = 19_video_caso_b2.mp4 (in questa cartella), frame = 0.
Il progetto, per gli import delle dipendenze, e' letto da PIANO_DETECTOR
(default: /Users/alessandrolocurcio/Downloads/piano-detector).

Esempio:
  python3 05_script_prova_ancora.py 01_codice_griglia_prospettica_NUOVO.py
"""
import importlib.util
import os
import sys

import cv2
import numpy as np

PROJ = os.environ.get("PIANO_DETECTOR", "/Users/alessandrolocurcio/Downloads/piano-detector")
sys.path.insert(0, PROJ)

QUI = os.path.dirname(os.path.abspath(__file__))
mod_path = sys.argv[1]
video = sys.argv[2] if len(sys.argv) > 2 else os.path.join(QUI, "19_video_caso_b2.mp4")
t = int(sys.argv[3]) if len(sys.argv) > 3 else 0

spec = importlib.util.spec_from_file_location("gvar", mod_path)
m = importlib.util.module_from_spec(spec)
sys.modules["gvar"] = m
spec.loader.exec_module(m)

cap = cv2.VideoCapture(video)
for _ in range(t + 1):
    ok, fr = cap.read()
cap.release()
g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
h, w = g.shape
H = m.H_iniziale(fr, 61)
H2, k2 = m.affina(g, H, m.rosso(fr), 3)
celle, neri = [], []
for n in list(m.BIANCHI) + list(m.NERI):
    c = m._celle(H2, n, 3)[1]
    cx, cy = float(c[:, 0].mean()), float(c[:, 1].mean())
    if 0 <= cx < w and -0.1 * h <= cy < h:
        celle.append((n, m.e_nero(n), cx, cy))
        if m.e_nero(n):
            neri.append((n, cx))
xs = [cx for _, _, cx, _ in celle]
print(f"modulo {mod_path}  frame {t}  {w}x{h}")
print(f"  NOTA_MIN..MAX = {m.NOTA_MIN}..{m.NOTA_MAX}   neri nel modello: {len(m.NERI)}")
print(f"  inlier affina = {k2}")
print(f"  celle in frame: {len(celle)}  x {min(xs):.0f}..{max(xs):.0f}")
if neri:
    print(f"  neri del modello in frame: {len(neri)}  note {min(n for n, _ in neri)}"
          f"..{max(n for n, _ in neri)}  x {min(x for _, x in neri):.0f}"
          f"..{max(x for _, x in neri):.0f}")
primi = sorted(celle)[:3]
ultimi = sorted(celle)[-3:]
print(f"  celle piu' a sinistra : {[(n, m.nome(n), round(cx)) for n, _, cx, _ in primi]}")
print(f"  celle piu' a destra   : {[(n, m.nome(n), round(cx)) for n, _, cx, _ in ultimi]}")
