"""video + griglia.json (+ mani.json) + modello.pt -> probabilita.json (probabilita' che ogni
tasto sia premuto, per frame). Con --note / --midi scrive direttamente le note riconosciute,
decodificate con isteresi (soglia di accensione e di spegnimento) e durata minima."""
import argparse, json
from pathlib import Path
import numpy as np, torch
from comune import *

a = argparse.ArgumentParser()
a.add_argument("--video", required=True); a.add_argument("--griglia", required=True)
a.add_argument("--mani", default=None); a.add_argument("--modello", default="modello.pt")
a.add_argument("-o", default="probabilita.json")
a.add_argument("--liscia", type=int, default=0, help="media mobile sui frame (0 = quella salvata nel modello)")
a.add_argument("--soglia-on", type=float, default=None, help="default: quella salvata nel modello")
a.add_argument("--soglia-off", type=float, default=None)
a.add_argument("--min-frame", type=int, default=None)
a.add_argument("--ignora-mani", type=int, default=0,
               help="1 = valuta tutti i tasti come se le dita fossero sempre visibili")
a.add_argument("--forza", type=int, default=0,
               help="1 = procedi anche se la griglia e' di un altro video (quasi sempre e' un errore)")
a.add_argument("--note", default=None, help="scrive anche le note riconosciute in un .json")
a.add_argument("--midi", default=None, help="scrive anche le note riconosciute in un .mid")
a.add_argument("--bpm", type=float, default=120.0)
a = a.parse_args()

ck = torch.load(a.modello, map_location="cpu"); dev = device(); net = carica_rete(ck, dev)
soglia_on = float(a.soglia_on if a.soglia_on is not None else ck.get("soglia", SOGLIA_ON))
soglia_off = float(a.soglia_off if a.soglia_off is not None else ck.get("soglia_off", SOGLIA_OFF))
min_frame = int(a.min_frame if a.min_frame is not None else ck.get("min_frame", MIN_FRAME))
finale = int(a.liscia or ck.get("liscia", 3))
raggio = float(ck.get("raggio", 2.5))
usa_mani = bool(ck.get("usa_mani", True))
dita = bool(a.mani) and usa_mani and not a.ignora_mani     # si usa la posizione delle dita?
print(f"modello {Path(a.modello).name}: rete v{getattr(net, 'versione', 1)}, movimento "
      f"{getattr(net, 'movimento', False)}, soglie {soglia_on:.2f}/{soglia_off:.2f}, liscia {finale}"
      + (f", val F1 nota {ck['f1_nota']:.3f}" if ck.get("f1_nota") else "")
      + (f", raggio {raggio:.2f}" if dita else ""))
if usa_mani and not a.mani and not a.ignora_mani:
    print("[i] senza --mani la rete vede «dita non viste» in ogni frame e guarda tutti i tasti: "
          "se hai mani.json passalo, e' piu' preciso e molto piu' veloce")
if a.mani and not usa_mani:
    print("[i] questo modello e' stato addestrato senza le dita: le posizioni delle dita non si usano")
gr = carica_griglia(a.griglia); n = gr["n_frame"]; mani = carica_mani(a.mani, n)
P, fps, n = probabilita_video(net, ck, a.video, gr, mani, dita, forza=bool(a.forza))
if finale > 1: P = liscia(P, finale)
note = decodifica(P, fps, soglia_on, soglia_off, min_frame)
fr = [{"f": j, "p": {str(k): round(float(P[j, k]), 3) for k in np.where(~np.isnan(P[j]))[0]}} for j in range(n)]
json.dump({"video": gr["video"], "fps": gr["fps"], "n_frame": n, "soglia": soglia_on, "soglia_off": soglia_off,
           "min_frame": min_frame, "raggio": raggio, "liscia": finale, "modello": Path(a.modello).name,
           "patch": {"w": PW, "h": PH, "margine": MARG, "ext": EXT}, "frames": fr},
          open(a.o, "w"), separators=(",", ":"))
print("scritto", a.o)
if a.note:
    json.dump({"video": gr["video"], "bpm": a.bpm, "soglia_on": soglia_on, "soglia_off": soglia_off,
               "min_frame": min_frame, "modello": Path(a.modello).name,
               "note": [{"nota": int(k), "idx": int(k) - 21, "inizio": round(float(t0), 4),
                         "fine": round(float(t1), 4), "frame": int(f0)} for k, t0, t1, f0 in note]},
              open(a.note, "w"), indent=1)
    print(f"scritte {len(note)} note in", a.note)
if a.midi:
    print(f"scritte {len(note)} note in", salva_midi_eventi([(k, t0, t1) for k, t0, t1, _ in note], a.midi, a.bpm))
print(f"note riconosciute: {len(note)}; frame con almeno un tasto guardato: "
      f"{int((~np.isnan(P)).any(1).sum())}/{n}")
