"""dataset/*.npz -> modello.pt. La validazione e' su VIDEO interi mai visti e si misura a
livello di NOTA: «quante note ha riconosciuto», non «quante patch di tasto».

Le soglie di decisione si scelgono su quel numero (non a occhio) e il modello salvato e'
quello che ha fatto meglio. L'aumento dei dati (`comune.augmenta`) simula l'errore vero della
griglia prospettica (10-20 px) e le differenze fra una ripresa e l'altra: e' quello che fa
funzionare la rete su video che non ha mai visto.
"""
import argparse, glob
from pathlib import Path
import numpy as np, torch, torch.nn.functional as F
from comune import *

a = argparse.ArgumentParser()
a.add_argument("--dati", default="dataset")
a.add_argument("--val", nargs="*", default=None,
               help="nomi (stem) dei pezzi di validazione; default: l'ultimo ~20%%")
a.add_argument("--epoche", type=int, default=30)
a.add_argument("--batch", type=int, default=128)
a.add_argument("--raggio", type=float, default=None,
               help="default: quello scritto nei dataset da 2_costruisci_dataset.py")
a.add_argument("--aug", type=float, default=1.0, help="forza dell'aumento dei dati (0 = spento)")
a.add_argument("--pazienza", type=int, default=0,
               help="quante epoche si aspetta senza migliorare prima di fermarsi (0 = automatico)")
a.add_argument("--movimento", type=int, default=1,
               help="1 = la rete vede anche il movimento fra i due frame (consigliato)")
a.add_argument("--semi", type=int, default=0, help="seme per la riproducibilita'")
a.add_argument("-o", default="modello.pt")
a = a.parse_args()

torch.manual_seed(a.semi); np.random.seed(a.semi)
fs = sorted(glob.glob(f"{a.dati}/*.npz")); assert fs, "nessun dataset"
nv = max(1, len(fs) // 5) if len(fs) > 1 else 0
val = [f for f in fs if Path(f).stem in a.val] if a.val is not None else fs[len(fs) - nv:]
tr = [f for f in fs if f not in val]

def pezzo(f):
    """Un dataset = un pezzo di un video: patch, etichette, numeri extra, note vere e fps."""
    try:
        d = np.load(f)
        for k in ("X", "y", "frame", "nota", "nero", "dist"):
            if k not in d.files: raise KeyError(k)
    except Exception as err:
        raise SystemExit(f"[!] {f} non e' un dataset di 2_costruisci_dataset.py ({err!r}). In "
                         f"--dati ci vanno SOLO i .npz dei pezzi: model.pt, probabilita.json e "
                         f"simili stanno altrove (es. una cartella per i modelli).")
    nero = d["nero"].astype(np.float32); dist = d["dist"].astype(np.float32)
    viste = (d["mani"] > 0).astype(np.float32) if "mani" in d.files else np.ones(len(nero), np.float32)
    rag = float(d["raggio"]) if "raggio" in d.files else float(a.raggio or 2.5)
    rit = float(d["ritardo"]) if "ritardo" in d.files else 0.0
    nota = np.asarray(d["nota"])
    return {"nome": Path(f).stem, "X": d["X"], "y": np.asarray(d["y"]).astype(np.float32),
            "nero": nero, "dist": dist, "viste": viste, "frame": np.asarray(d["frame"]),
            "nota": nota, "eventi": [e for e in eventi_da_npz(d) if e[0] in set(nota.tolist())],
            "fps": float(d["fps"]) if "fps" in d.files else 30.0, "raggio": rag, "ritardo": rit,
            "usa_mani": bool(d["usa_mani"]) if "usa_mani" in d.files else ("mani" in d.files)}

P_tr = [pezzo(f) for f in tr]; P_val = [pezzo(f) for f in val] if val else []
raggi = sorted({p["raggio"] for p in P_tr + P_val})
if len(raggi) > 1:                    # ogni pezzo misura il suo (auto), ma il numero deve essere UNO:
    det = ", ".join(p["nome"] + " " + f"{p['raggio']:.1f}" for p in P_tr + P_val)
    print(f"[i] raggi diversi fra i pezzi ({det}): si guarda fino a {raggi[-1]:.1f} larghezze di tasto "
          f"(il piu' grande, cosi' nessun tasto utile resta fuori) e la distanza si normalizza con "
          f"quello. I pezzi con raggio piu' piccolo hanno meno campioni lontani: per averli omogenei "
          f"rifalli tutti con --raggio {raggi[-1]:.1f}.")
raggio = raggi[-1] if raggi else 2.5
if a.raggio is not None and abs(a.raggio - raggio) > 1e-6:
    print(f"[i] --raggio {a.raggio} != {raggio} usato per costruire i dataset: si usa quello dei "
          f"dataset (e' quello che decide dove si guarda, a addestramento e a inferenza).")
for p in P_tr + P_val:                # la distanza si normalizza col raggio COMUNE: cosi' la stessa
    dmin = np.where(p["viste"] > 0,   # distanza vale lo stesso per tutti i pezzi (e per l'inferenza)
                    np.minimum(p["dist"] / raggio, MANI_ASSENTI), MANI_ASSENTI)
    p["E"] = np.stack([p["nero"], dmin, p["viste"]], 1).astype(np.float32)
ritardi = sorted({round(p["ritardo"], 4) for p in P_tr + P_val})
ritardo = float(ritardi[len(ritardi) // 2]) if ritardi else 0.0
if len(ritardi) > 1:
    print(f"[i] ritardi MIDI diversi fra i pezzi {ritardi}: nel modello salvo {ritardo:+.3f} s (il "
          f"mediano). 5_valuta.py lo usa da solo: se un pezzo ha un ritardo suo, passagli --ritardo.")
Xt = np.concatenate([p["X"] for p in P_tr]); yt = np.concatenate([p["y"] for p in P_tr])
Et = np.concatenate([p["E"] for p in P_tr])
Xv = np.concatenate([p["X"] for p in P_val]) if P_val else None
yv = np.concatenate([p["y"] for p in P_val]) if P_val else None
Ev = np.concatenate([p["E"] for p in P_val]) if P_val else None
print(f"train {len(yt)} ({yt.mean() * 100:.1f}% premuti) da {len(P_tr)} pezzi: "
      + ", ".join(p["nome"] for p in P_tr))
print("val   " + (f"{len(yv)} da {len(P_val)} pezzi: "
      + ", ".join(f"{p['nome']} ({len(p['eventi'])} note vere)" for p in P_val) if P_val else
      "0 pezzi  <- senza un pezzo tenuto fuori NON c'e' nessuna misura onesta") + "")
if any(not p["usa_mani"] for p in P_tr):
    print("[!] fra i dataset di addestramento ce n'e' almeno uno costruito senza le dita (--mani): "
          "per quei campioni la rete non sa distinguere «mani non riconosciute» da «dito sul tasto».")
note_ok = bool(P_val) and any(p["eventi"] for p in P_val)
if P_val and not note_ok:
    print("[!] nessun pezzo di validazione ha le note vere (dataset vecchi: li rifai con "
          "2_costruisci_dataset.py, che ora salva MIDI, fps e note). Si andra' avanti scegliendo il "
          "modello sull'F1 delle patch di tasto, che NON dice quante note riconosce.")
dev = device()
net = Rete(movimento=bool(a.movimento)).to(dev)
net.mu = float(Xt.mean() / 255.0)                # media e deviazione standard del train:
net.sigma = max(float(Xt.std() / 255.0), 1e-3)   # normalizzano l'ingresso e finiscono nel .pt
opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-3)
passi = max(1, (len(yt) + a.batch - 1) // a.batch)
sched = torch.optim.lr_scheduler.OneCycleLR(opt, 4e-3, total_steps=a.epoche * passi)
pos = float(min((1 - yt.mean()) / max(yt.mean(), 1e-3), 8.0))
pw = torch.tensor(pos, device=dev, dtype=torch.float32)   # MPS non supporta float64
print(f"rete: movimento {bool(a.movimento)}, ingresso normalizzato (media {net.mu:.3f}, dev {net.sigma:.3f}), "
      f"raggio {raggio:.2f}, peso dei positivi {pos:.2f}, {passi} passi per epoca, fino a {a.epoche} epoche")

def migliore_soglia(p, y):
    """Soglia sulle patch di tasto che rende massimo l'F1: e' la misura di controllo."""
    r = max(((2 * ((p >= s) & (y == 1)).sum() / max((p >= s).sum() + (y == 1).sum(), 1), s) for s in np.linspace(.1, .9, 33)))
    s = r[1]; pr = ((p >= s) & (y == 1)).sum() / max((p >= s).sum(), 1); rc = ((p >= s) & (y == 1)).sum() / max((y == 1).sum(), 1)
    return float(r[0]), float(s), float(pr), float(rc)

def P_del_pezzo(pz, prob):
    """Probabilita' per frame e tasto (NaN dove quel tasto non e' stato guardato)."""
    P = np.full((int(pz["frame"].max()) + 1, 128), np.nan, np.float32)
    P[pz["frame"], pz["nota"]] = prob
    return P

def metrica_note(Pm, soglia_on, soglia_off):
    """Precision, recall e F1 contati sulle NOTE di tutti i pezzi di validazione."""
    giu = tro = ver = 0
    for pz, P in Pm:
        m = confronta_note(decodifica(P, pz["fps"], soglia_on, soglia_off), pz["eventi"])
        giu += m["n_giuste"]; tro += m["n_trovate"]; ver += m["n_vere"]
    pr = giu / tro if tro else 0.0; rc = giu / ver if ver else 0.0
    return (2 * pr * rc / (pr + rc) if pr + rc else 0.0), pr, rc, giu, tro, ver

def salva(percorso, note_f1, s_on, s_off, frame_f1, soglia_frame, ep):
    torch.save({"stato": net.state_dict(), "versione": net.versione,
                "soglia": float(s_on), "soglia_off": float(s_off),
                "soglia_frame": float(soglia_frame), "min_frame": MIN_FRAME, "liscia": 3,
                "raggio": raggio, "PW": PW, "PH": PH, "LAG": LAG, "movimento": bool(a.movimento),
                "ritardo": float(ritardo),
                "mu": net.mu, "sigma": net.sigma, "epoca": ep, "f1_nota": float(note_f1),
                "f1_frame": float(frame_f1), "aug": a.aug,
                "usa_mani": bool(all(p["usa_mani"] for p in P_tr)),
                "train": [p["nome"] for p in P_tr], "val": [p["nome"] for p in P_val]}, percorso)

migliore = {"f1": -1.0, "stato": None, "on": SOGLIA_ON, "off": SOGLIA_OFF, "frame_f1": 0.0, "ep": 0}
pazienza = a.pazienza or max(3, a.epoche // 5)
senza = 0
for ep in range(1, a.epoche + 1):
    net.train(); perm = np.random.permutation(len(yt)); somma = 0.0
    for i in range(0, len(perm), a.batch):
        ix = np.sort(perm[i:i + a.batch])
        x = augmenta(torch.from_numpy(Xt[ix]).to(dev).float() / 255, a.aug)
        e = torch.from_numpy(Et[ix]).to(dev)
        loss = F.binary_cross_entropy_with_logits(net(x, e), torch.from_numpy(yt[ix]).to(dev), pos_weight=pw)
        opt.zero_grad(set_to_none=True); loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
        opt.step(); sched.step(); somma += loss.item() * len(ix)
    riga = f"epoca {ep:2d}  loss {somma / len(perm):.4f}"
    if P_val:
        f1_frame, sg, pr, rc = migliore_soglia(predici_rete(net, Xv, Ev, dev), yv)
        riga += f" | val F1 {f1_frame:.3f} (P {pr:.2f} R {rc:.2f}, soglia {sg:.2f})"
        if note_ok:
            Pm = [(pz, liscia(P_del_pezzo(pz, predici_rete(net, pz["X"], pz["E"], dev)), 3)) for pz in P_val]
            prova = max((metrica_note(Pm, float(s_on), float(max(s_on - 0.1, 0.05))) + (float(s_on), float(max(s_on - 0.1, 0.05)))
                         for s_on in np.arange(0.30, 0.81, 0.05)), key=lambda v: v[0])
            nf1, npr, nrc, ngi, ntr, nve, s_on, s_off = prova
            riga += (f" | nota F1 {nf1:.3f} (P {npr:.2f} R {nrc:.2f}, {ngi}/{ntr} contro {nve} note vere, "
                     f"soglie {s_on:.2f}/{s_off:.2f})")
            chiave = nf1                                   # si tiene il modello che riconosce piu' note
        else:                                              # dataset vecchi: solo l'F1 dei tasti
            chiave, s_on, s_off = f1_frame, sg, max(sg - 0.15, 0.05)
        if chiave > migliore["f1"]:
            migliore = {"f1": chiave, "on": s_on, "off": s_off, "frame_f1": f1_frame, "ep": ep,
                        "stato": {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}}
            senza = 0; salva(a.o, chiave, s_on, s_off, f1_frame, sg, ep)
        else:
            senza += 1
    print(riga, flush=True)
    if P_val and senza >= pazienza:
        print(f"[i] nessun miglioramento per {pazienza} epoche: mi fermo e tengo quello che ha fatto meglio")
        break
if P_val:
    net.load_state_dict(migliore["stato"])
    print(f"modello scelto: epoca {migliore['ep']}, "
          + (f"F1 sulle note {migliore['f1']:.3f}" if note_ok else f"F1 sulle patch di tasto {migliore['f1']:.3f}")
          + f" (F1 patch {migliore['frame_f1']:.3f}), soglie {migliore['on']:.2f}/{migliore['off']:.2f}")
else:
    salva(a.o, 0.0, SOGLIA_ON, SOGLIA_OFF, 0.0, 0.5, a.epoche)
    print("nessun pezzo di validazione: salvo l'ultima epoca, ma senza un video mai visto non si "
          "puo' sapere quanto vale questo modello")
print("salvato", a.o)
