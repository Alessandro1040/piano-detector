"""
Copertura: quanti dei neri REALI della tastiera inquadrata sono rappresentabili dal modello
(NOTA_MIN..NOTA_MAX)? Confronta, sulla stessa riga, i centri dei neri del modello con i run
scuri reali e dice quanti ne restano fuori a sinistra e a destra.

Uso: python3 06_script_copertura_modello.py <run_dir> <video>
`run_dir` = cartella di uscita del motore (deve contenere `griglia.json`).
Il progetto e' letto da PIANO_DETECTOR (default /Users/alessandrolocurcio/Downloads/piano-detector).

Esempio (misura del difetto di copertura, vedi `11_prova_copertura_modello.log`):
  python3 04_codice_motore_prospettica.py 19_video_caso_b2.mp4 -o /tmp/run_b2
  python3 06_script_copertura_modello.py /tmp/run_b2 19_video_caso_b2.mp4
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

PROJ = os.environ.get("PIANO_DETECTOR", "/Users/alessandrolocurcio/Downloads/piano-detector")
sys.path.insert(0, PROJ)
import griglia_prospettica as G  # noqa: E402

run = Path(sys.argv[1])
video = sys.argv[2]
doc = json.loads((run / "griglia.json").read_text())
frames = doc["frames"]
cap = cv2.VideoCapture(video)

for t in (0, 60):
    if t >= len(frames):
        break
    cap.set(cv2.CAP_PROP_POS_FRAMES, t)
    ok, fr = cap.read()
    if not ok:
        break
    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    T = G._soglia(g)
    model_b, model_w = [], []
    for nk, d in frames[t]["tasti"].items():
        c = np.array(d["celle_profondita"][1])
        cx, cy = float(c[:, 0].mean()), float(c[:, 1].mean())
        if 0 <= cx < w:
            (model_b if d["nero"] else model_w).append((int(nk), cx, cy))
    if not model_b:
        continue
    y = int(np.median([cy for _, _, cy in model_b]))
    lo, hi = max(2.0, 0.003 * w), 0.075 * w
    reali = [((a + b) / 2.0, b - a) for a, b in G._runs(g[y] < T) if lo <= b - a <= hi]
    xm0, xm1 = min(x for _, x, _ in model_b), max(x for _, x, _ in model_b)
    print(f"\nframe {t}: riga neri y={y}")
    print(f"  modello : {len(model_b):2d} neri, x {xm0:.0f}..{xm1:.0f} "
          f"(note {min(n for n, _, _ in model_b)}..{max(n for n, _, _ in model_b)})")
    print(f"  reali   : {len(reali):2d} neri, x {min(r[0] for r in reali):.0f}.."
          f"{max(r[0] for r in reali):.0f}")
    fuori_sx = [r for r in reali if r[0] < xm0 - 1]
    fuori_dx = [r for r in reali if r[0] > xm1 + 1]
    print(f"  fuori a sinistra del modello: {len(fuori_sx)}  "
          f"x={[round(r[0]) for r in fuori_sx]}")
    print(f"  fuori a destra  del modello: {len(fuori_dx)}  "
          f"x={[round(r[0]) for r in fuori_dx]}")
    passo = float(np.median(np.diff(sorted(x for _, x, _ in model_w)))) if len(model_w) > 3 else float('nan')
    print(f"  passo bianco (modello, celle): {passo:.2f} px   "
          f"-> sinistra non coperta ≈ {len(fuori_sx)} tasti neri "
          f"(~{len(fuori_sx)*12/5:.0f} tasti totali)")
cap.release()
