"""Esempio: leggere `*_griglia_nel_tempo.npz` e `*_note.json` prodotti dal passo 0.

    python leggi_griglia_nel_tempo.py <prefisso>            # es. out/pezzo_preparato
    python leggi_griglia_nel_tempo.py <prefisso> C4 2.5     # dove sta C4 al secondo 2,5

Il file contiene, per ogni nota e per ogni fotogramma del video ORIGINALE, i 4 angoli del rettangolo
(retro-sinistra, retro-destra, fronte-destra, fronte-sinistra), e per il video PREPARATO (dove la
tastiera sta ferma) un solo rettangolo per nota.
"""
import json
import sys

import numpy as np


def carica(prefisso):
    d = np.load(prefisso + "_griglia_nel_tempo.npz")
    note = json.load(open(prefisso + "_note.json", encoding="utf-8"))
    return d, note


def trova_nota(note, nome):
    for i, n in enumerate(note["note"]):
        if n["nome"].lower() == nome.lower():
            return i, n
    raise SystemExit(f"nota {nome} non presente (le note vanno da {note['prima_nota']} a {note['ultima_nota']})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    d, note = carica(sys.argv[1])
    print(f"{note['numero_note']} note, da {note['prima_nota']} a {note['ultima_nota']}; "
          f"{len(d['tempo_s'])} fotogrammi; video preparato {d['dim_preparato'].tolist()}; "
          f"nomi {'certi' if note['nomi_certi'] else 'ipotizzati'}")
    if len(sys.argv) >= 4:
        k, info = trova_nota(note, sys.argv[2])
        t = int(np.argmin(np.abs(d["tempo_s"] - float(sys.argv[3]))))
        print(f"{info['nome']} (MIDI {info['midi']}, {info['tipo']}), visto nel video: {info['visto_nel_video']}")
        print(f"  nel video originale al fotogramma {int(d['indice_fotogramma'][t])} ({d['tempo_s'][t]:.2f} s), "
              f"visibilita' {int(d['visibile'][t, k])} (0 fuori, 1 in parte, 2 dentro):")
        print(np.round(d["poligoni_originale"][t, k], 1))
        print("  nel video preparato (fermo):")
        print(np.round(d["poligoni_preparato"][k], 1))
