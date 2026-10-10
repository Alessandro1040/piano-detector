"""Valuta un modello.pt su VIDEO interi (meglio se mai visti) contro il MIDI vero del pezzo.

Per ogni video fa l'inferenza completa, decodifica le probabilita' in note (isteresi + durata
minima) e le confronta con gli attacchi veri del MIDI: precision, recall, F1 e errore sui
tempi. E' l'unica misura che dice davvero quanto funziona: l'F1 sulle patch di tasto puo'
essere alto e le note comunque sbagliate.

Con --cerca prova anche una griglia di soglie e dice quale sarebbe la migliore su questi
video: se il guadagno e' grosso il modello e' solo da ritarare, se non cambia niente il
problema sono i dati. `--ritardo` deve essere lo stesso usato per costruire il dataset.
"""
import argparse, json
from pathlib import Path
import numpy as np, torch
from comune import *

a = argparse.ArgumentParser()
a.add_argument("--modello", default="modello.pt")
a.add_argument("--video", nargs="+", required=True)
a.add_argument("--griglia", nargs="+", required=True, help="una sola per tutti, oppure una per video")
a.add_argument("--midi", nargs="+", required=True, help="uno per video, nello stesso ordine")
a.add_argument("--mani", nargs="*", default=None, help="una sola per tutti, oppure una per video")
a.add_argument("--ritardo", type=float, default=None,
               help="stesso ritardo (s) usato per costruire il dataset: allinea MIDI e video "
                    "(default: quello salvato nel modello da 3_addestra.py)")
a.add_argument("--liscia", type=int, default=0, help="0 = quella salvata nel modello")
a.add_argument("--min-frame", type=int, default=None)
a.add_argument("--cerca", type=int, default=1, help="1 = cerca anche le soglie migliori su questi video")
a.add_argument("--salva-note", default=None, help="scrive un json con note riconosciute e note vere")
a.add_argument("--forza", type=int, default=0,
               help="1 = procedi anche se la griglia e' di un altro video (quasi sempre e' un errore)")
a = a.parse_args()

assert len(a.midi) == len(a.video), "--midi: uno per ogni --video, nello stesso ordine"

def uno(elenco, i, quanti):
    """Accetta un file solo (vale per tutti i video) oppure uno per video."""
    return None if elenco is None else (elenco[i] if len(elenco) == quanti else elenco[0])

ck = torch.load(a.modello, map_location="cpu"); dev = device(); net = carica_rete(ck, dev)
soglia_on = float(ck.get("soglia", SOGLIA_ON)); soglia_off = float(ck.get("soglia_off", SOGLIA_OFF))
min_frame = int(a.min_frame if a.min_frame is not None else ck.get("min_frame", MIN_FRAME))
lisciata = int(a.liscia or ck.get("liscia", 3))
usa_mani = bool(ck.get("usa_mani", True))
ritardo = float(ck.get("ritardo", 0.0)) if a.ritardo is None else float(a.ritardo)
print(f"modello {Path(a.modello).name}: rete v{getattr(net, 'versione', 1)}, soglie "
      f"{soglia_on:.2f}/{soglia_off:.2f}, liscia {lisciata}, durata minima {min_frame} frame"
      + (f", addestrato su {len(ck['train'])} pezzi e misurato su {', '.join(ck.get('val') or ['nessuno'])}"
         if ck.get("train") else ""))
print(f"ritardo MIDI-video {ritardo:+.3f} s ({'passato a mano' if a.ritardo is not None else 'quello del modello'})")

esiti = []          # (nome, note riconosciute, note vere, fps, probabilita')
for i, (vid, mid) in enumerate(zip(a.video, a.midi)):
    gr = carica_griglia(uno(a.griglia, i, len(a.video))); n = gr["n_frame"]
    mp = uno(a.mani, i, len(a.video)); mani = carica_mani(mp, n)
    dita = bool(mp) and usa_mani
    print(f"[{Path(vid).name}] {n} frame, " + (f"dita da {Path(mp).name}" if dita else "senza dita"))
    P, fps, n = probabilita_video(net, ck, vid, gr, mani, dita, forza=bool(a.forza))
    if lisciata > 1: P = liscia(P, lisciata)
    trovate = decodifica(P, fps, soglia_on, soglia_off, min_frame)
    vere = [(int(k), t0 + ritardo, t1 + ritardo) for k, t0, t1 in note_midi(mid)]
    if dita:        # le note vere si contano solo sui tasti che la rete poteva davvero guardare
        visti = set(int(k) for k in np.nonzero(~np.all(np.isnan(P), 0))[0])
        quante = len(vere); vere = [e for e in vere if e[0] in visti]
        if quante != len(vere): print(f"  {quante - len(vere)} note vere fuori dai tasti guardati: non contate")
    esiti.append((Path(vid).name, trovate, vere, fps, P))
    m = confronta_note(trovate, vere)
    print(f"  riconosciute {m['n_trovate']} contro {m['n_vere']} vere | P {m['precision']:.3f} "
          f"R {m['recall']:.3f} F1 {m['f1']:.3f} | {m['n_extra']} in piu', {m['n_mancate']} mancate"
          + (f" | onset {m['onset_mediano_ms']:+.0f} ms (5-95%: {m['onset_5_95_ms'][0]:+.0f}/"
             f"{m['onset_5_95_ms'][1]:+.0f})" if m["onset_mediano_ms"] is not None else ""))


def totale(esiti, so, sf):
    """Precision, recall e F1 contati su tutte le note di tutti i video."""
    giu = tro = ver = 0
    for _nome, _tro, _ver, fps, P in esiti:
        m = confronta_note(decodifica(P, fps, so, sf, min_frame), _ver)
        giu += m["n_giuste"]; tro += m["n_trovate"]; ver += m["n_vere"]
    pr = giu / tro if tro else 0.0; rc = giu / ver if ver else 0.0
    return (2 * pr * rc / (pr + rc) if pr + rc else 0.0), pr, rc, giu, tro, ver

f1, pr, rc, giu, tro, ver = totale(esiti, soglia_on, soglia_off)
print(f"TOTALE: F1 {f1:.3f} (P {pr:.3f} R {rc:.3f}) — {giu} note giuste su {tro} riconosciute e {ver} vere")
if a.cerca:
    prove = [(totale(esiti, float(so), float(sf)), float(so), float(sf))
             for so in np.arange(0.25, 0.86, 0.05) for sf in (so - 0.05, so - 0.15, so - 0.25) if sf > 0.02]
    mig = max(prove, key=lambda v: v[0][0])
    print(f"migliori soglie su questi video: F1 {mig[0][0]:.3f} (P {mig[0][1]:.3f} R {mig[0][2]:.3f}) "
          f"con {mig[1]:.2f}/{mig[2]:.2f}")
    print("[i] le soglie salvate sono gia' vicine al meglio: se le note sbagliano il problema e' il "
          "modello (servono piu' video), non la soglia" if mig[0][0] < f1 + 0.02 else
          "[i] con altre soglie si guadagna parecchio: rifai l'addestramento con piu' pezzi, cosi' la "
          "scelta delle soglie non dipende da un video solo")
if a.salva_note:
    json.dump({"modello": Path(a.modello).name, "soglie": [soglia_on, soglia_off], "min_frame": min_frame,
               "pezzi": [{"video": nome,
                          "riconosciute": [{"nota": int(k), "inizio": round(t0, 4), "fine": round(t1, 4)}
                                           for k, t0, t1, _f in tr],
                          "vere": [{"nota": int(k), "inizio": round(t0, 4), "fine": round(t1, 4)}
                                   for k, t0, t1 in ve]} for nome, tr, ve, _f, _P in esiti]},
              open(a.salva_note, "w"), indent=1)
    print("scritto", a.salva_note)
