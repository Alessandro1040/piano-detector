"""
Identita' delle note: il gruppo da DUE neri piu' vicino al centro della tastiera e' davvero
C#4-D#4?  Dalla geometria dei neri misurata sul frame si ricostruisce il pattern 2-neri /
3-neri, si individua il gruppo da due neri e si confronta con la posizione che il modello
associa a ogni C#: cosi' si sa con che ottava ha agganciato il motore.

Uso: python3 07_script_identita_ottava.py <video>
Il progetto e' letto da PIANO_DETECTOR (default /Users/alessandrolocurcio/Downloads/piano-detector).

Misura del difetto di ottava (vedi `10_prova_identita_ottava.log`):
  python3 07_script_identita_ottava.py 19_video_caso_b2.mp4
"""
import os
import sys

import cv2
import numpy as np

PROJ = os.environ.get("PIANO_DETECTOR", "/Users/alessandrolocurcio/Downloads/piano-detector")
sys.path.insert(0, PROJ)
import griglia_prospettica as G  # noqa: E402


def neri_riga(g, T, y, lo, hi):
    return [((a + b) / 2.0, b - a) for a, b in G._runs(g[y] < T) if lo <= b - a <= hi]


def gruppi_da_neri(g, T, w, y_neri, lo, hi):
    """Da una riga sui neri: passo bianco, gruppi (2 o 3 neri) e loro centri."""
    cs = [c for c, _ in neri_riga(g, T, y_neri, lo, hi)]
    if len(cs) < 6:
        return None
    cs = np.array(sorted(cs))
    sp = np.diff(cs)
    # passo bianco: spaziatura piu' piccola fra neri vicini (1 bianco dentro un gruppo)
    vicino = sp[sp < np.median(sp) * 1.35]
    passo = float(np.median(vicino))
    gruppi, cur = [], [cs[0]]
    for c, d in zip(cs[1:], sp):
        if d < passo * 1.4:
            cur.append(c)
        else:
            gruppi.append(cur)
            cur = [c]
    gruppi.append(cur)
    return passo, gruppi


def main():
    p = sys.argv[1]
    cap = cv2.VideoCapture(p)
    ok, fr = cap.read()
    cap.release()
    g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    T = G._soglia(g)
    lo, hi = max(2.5, 0.004 * w), 0.075 * w
    print(f"{p.split('/')[-1]}  {w}x{h}  T={T:.0f}", flush=True)

    H = G.H_iniziale(fr, 61)
    passo_mod = float(np.linalg.norm(G.proietta(H, [(1.0, 0.0)])[0]
                                     - G.proietta(H, [(0.0, 0.0)])[0]))
    print(f"ancora del motore: passo modello={passo_mod:.2f}px  nota_gruppo2=61 (C#4)", flush=True)

    # riga sui neri: la piu' densa di neri 'da tasto' nel frame
    mig = None
    for y in range(int(0.2 * h), int(0.75 * h)):
        r = neri_riga(g, T, y, lo, hi)
        if mig is None or len(r) > len(mig[1]):
            mig = (y, r)
    y_neri = mig[0]
    res = gruppi_da_neri(g, T, w, y_neri, lo, hi)
    if res is None:
        print("!! pochi neri per ricostruire il pattern")
        return
    passo_reale, gruppi = res
    print(f"riga neri y={y_neri}: {sum(len(x) for x in gruppi)} neri, "
          f"passo bianco misurato={passo_reale:.2f}px, "
          f"scarto vs modello={100*(passo_mod/passo_reale-1):+.1f}%", flush=True)

    due = [gp for gp in gruppi if len(gp) == 2]
    tre = [gp for gp in gruppi if len(gp) == 3]
    print(f"gruppi: {len(due)} da 2 neri, {len(tre)} da 3 neri "
          f"(su una tastiera completa: 7 gruppi da 2 e 7 da 3)", flush=True)
    if not due:
        print("!! nessun gruppo da 2 neri")
        return
    # il gruppo da 2 neri piu' vicino al centro del frame: cosa e' davvero?
    g2 = min(due, key=lambda gp: abs(np.mean(gp) - w / 2))
    print(f"gruppo da 2 neri piu' vicino al centro: primo nero a x={g2[0]:.1f} "
          f"(centro frame x={w/2:.0f})", flush=True)
    # posizione di una nota nota nel modello: x = proiezione di u_nero(n)
    def x_mod(n):
        u = G.u_nero(n)
        return float(G.proietta(H, [(u, 0.0)])[0][0])
    x_c4 = x_mod(61)          # C#4 nel modello
    print(f"modello: x(C#4)={x_c4:.1f}  -> scarto dal gruppo scelto "
          f"{x_c4 - g2[0]:+.1f}px ({abs(x_c4-g2[0])/passo_reale:+.2f} bianchi)", flush=True)
    # quale C# del modello dista un numero intero di ottave dal gruppo?
    for dc in (-24, -12, 0, 12, 24):
        if not (G.NOTA_MIN <= 61 + dc <= G.NOTA_MAX):
            continue
        x = x_mod(61 + dc)
        print(f"   se il gruppo fosse {G.nome(61+dc)}: x_modello={x:.1f} "
              f"(scarto {x - g2[0]:+.1f}px = {(x-g2[0])/passo_reale:+.2f} bianchi)", flush=True)


if __name__ == "__main__":
    main()
