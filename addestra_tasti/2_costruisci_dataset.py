"""video + griglia.json + MIDI (+ mani.json) -> dataset/NOME.npz  (patch dei tasti vicini alle mani + etichetta premuto/no)."""
import argparse, collections
from pathlib import Path
import cv2, numpy as np
from comune import *

def stima_ritardo(video, gr, ev, fps, n, max_s=1.5):
    P = np.array([t["poligono"] for t in gr["frames"][0]["tasti"].values()]).reshape(-1, 2)
    x0, y0 = np.maximum(P.min(0), 0).astype(int); x1, y1 = P.max(0).astype(int)
    _, it = frames(video); prev, m = None, []
    for f in it:
        g = cv2.cvtColor(f[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        m.append(0 if prev is None else np.abs(g - prev).mean()); prev = g
    m = np.convolve(m[:n], np.ones(3) / 3, "same"); m = (m - m.mean()) / (m.std() + 1e-6)
    best = (-9, 0)
    for s in range(-int(max_s * fps), int(max_s * fps) + 1):
        o = np.zeros(len(m))
        for _, t0, _ in ev:
            k = int(round(t0 * fps)) + s
            if 0 <= k < len(m): o[k] = 1
        o = np.convolve(o, np.ones(3) / 3, "same"); o = (o - o.mean()) / (o.std() + 1e-6)
        c = float((m * o).mean())
        if c > best[0]: best = (c, s)
    print(f"ritardo stimato {best[1] / fps:+.3f} s (correlazione {best[0]:.2f})")
    return best[1] / fps, float(best[0])

a = argparse.ArgumentParser()
a.add_argument("--video", required=True); a.add_argument("--griglia", required=True)
a.add_argument("--midi", required=True); a.add_argument("--mani", default=None)
a.add_argument("--out", default=None); a.add_argument("--forza", type=int, default=0,
               help="1 = procedi anche se la griglia e' di un altro video (quasi sempre e' un errore)")
a.add_argument("--ritardo", default="0",
               help="secondi da sommare al tempo MIDI per allinearlo al video, oppure 'auto'")
a.add_argument("--raggio", default="auto",
               help="'auto' (consigliato) = si misura quanto stanno lontani dalle dita i tasti premuti "
                    "e si tiene il 90 per cento (2.5 a mano buttava via oltre meta' dei premuti); un "
                    "numero = larghezze di tasto dal polpastrello")
a.add_argument("--corr-minima", type=float, default=0.3,
               help="con --ritardo auto: sotto questa correlazione l'allineamento non si applica")
a.add_argument("--p-neg", type=float, default=0.4, help="frazione di negativi tenuti (i positivi si tengono tutti)")
a.add_argument("--bilanciamento", type=int, default=1,
               help="1 = ogni tasto porta piu' o meno gli stessi negativi (consigliato); 0 = come prima")
a.add_argument("--tieni-lontani", type=int, default=0,
               help="1 = tiene anche i tasti premuti oltre il raggio; a inferenza quei tasti NON "
                    "vengono guardati, quindi quasi mai e' quello che vuoi: meglio alzare --raggio")
a.add_argument("--disegna", type=int, default=0,
               help="N = salva N immagini di controllo (tasti premuti secondo il MIDI in rosso sui "
                    "frame veri) in dataset/allineamento/: si guardano per controllare a occhio che "
                    "il ritardo MIDI-video sia giusto, prima di addestrare")
a = a.parse_args()

gr = carica_griglia(a.griglia); BW = gr["modello"]["BW"]; fps, _ = frames(a.video)
n = controlla_video(a.video, gr, a.forza)     # griglia e video devono essere dello stesso video
mani = carica_mani(a.mani, n); ev = note_midi(a.midi)
if not ev:
    raise SystemExit(
        f"[!] {Path(a.midi).name} non contiene nessuna nota: con un MIDI vuoto non si puo' "
        f"costruire un dataset (nessun campione 'premuto' e nessuna nota vera su cui misurare).\n"
        f"  - e' il MIDI VERO di questa esecuzione? I song.mid che escono dai motori di "
        f"trascrizione sono le loro PREVISIONI, non la verita': se li usi come riferimento "
        f"insegni alla rete a copiare i suoi stessi errori.\n"
        f"  - se il brano non ha note (silenzio), togli il pezzo dal corso.")
_riff = Path(a.midi)
if _riff.name.lower() == "song.mid":
    print("[!] il MIDI di riferimento si chiama song.mid: e' il nome che danno i motori di "
          "trascrizione alla LORO uscita (previsioni, non verita'). Se non e' il MIDI vero di QUESTA "
          "esecuzione, la rete impara a copiare anche gli errori del motore e non potra' mai essere "
          "meglio di lui.", flush=True)
for _v in sorted(_riff.parent.glob("*.json")):
    if _v.name in ("notes.json", "probabilita.json", "sagome.json", "griglia.json"):
        print(f"[!] accanto al MIDI c'e' {_v.name}: e' una cartella di uscita di un motore. Se questo "
              f"MIDI viene da li', non e' una verita' a terra: serve il .mid dell'esecuzione vera "
              f"(quello che ha suonato la persona nel video).", flush=True)
        break
if a.ritardo == "auto":
    rit, corr = stima_ritardo(a.video, gr, ev, fps, n)
    if corr < a.corr_minima:                 # allineamento non attendibile: NON si applica
        print(f"[!] correlazione {corr:.2f} < {a.corr_minima}: ritardo NON applicato (uso 0). "
              f"Un ritardo sbagliato sposta le etichette e rovina il dataset: qui si perde solo "
              f"l'allineamento fine. Per correggerlo a mano registra il video con UNA NOTA ISOLATA "
              f"all'inizio e passa --ritardo SECONDI (positivo = il video e' in ritardo sul MIDI).",
              flush=True)
        rit = 0.0
else:
    rit = float(a.ritardo)
print(f"ritardo usato per le etichette: {rit:+.3f} s")
Y = etichette(ev, fps, n, rit)

# --- il raggio: quanto lontano dal polpastrello si guarda (decide anche l'inferenza) ---
# I tasti premuti dalle dita stanno a 3-8 larghezze di tasto, non a 2.5: con un raggio piccolo si
# buttano via proprio i campioni 'premuto' e la rete non impara a riconoscerli. Con 'auto' si
# misura la distanza dei premuti (dita visibili) su TUTTO il pezzo e si tiene il 90%.
if str(a.raggio).strip().lower() == "auto":
    if a.mani:
        dd = [float(dist_mani(t, BW, mani[j])) for j in range(min(n, len(gr["frames"])))
              for k, t in gr["frames"][j]["tasti"].items() if Y[j, int(k)] and mani[j]]
        raggio, avviso = stima_raggio(dd)
        print(f"raggio scelto da 'auto': {raggio:.1f} larghezze di tasto, misurato su {len(dd)} tasti "
              f"premuti con le dita visibili (il 90% sta piu' vicino di questo)")
        if avviso:
            print("[!] " + avviso)
    else:
        raggio = 2.5                                  # senza --mani non si filtra niente: non conta
        print("raggio: nessun --mani, quindi non si scarta nessun tasto (il raggio non conta)")
else:
    raggio = float(str(a.raggio).replace(",", "."))
    print(f"raggio scelto a mano: {raggio:.1f} larghezze di tasto")

# --- 1) si guardano solo i numeri (nessun video): quali tasti, e se sono premuti ---
cand, fuori, fuori_senza_mani, dist_fuori = [], 0, 0, []
for j in range(min(n, len(gr["frames"]))):
    viste = bool(mani[j])
    for k, t in gr["frames"][j]["tasti"].items():
        pos = bool(Y[j, int(k)])
        d = dist_mani(t, BW, mani[j]) if a.mani else 0.0
        if d > raggio and not (pos and a.tieni_lontani):
            fuori += pos
            if pos:                                      # perche' e' stato buttato: per capirlo dopo
                if viste: dist_fuori.append(float(d))    # le mani c'erano ma il tasto era lontano
                else: fuori_senza_mani += 1              # in quel frame non si vedono le mani
            continue                                     # lontano dalle mani: non si usa
        cand.append((j, int(k), pos, float(t["nero"]), float(d), viste))

# --- 2) quali negativi tenere: con --bilanciamento ogni tasto pesa uguale ---
rng = np.random.default_rng(0)
if a.bilanciamento:
    tenere = np.zeros(len(cand), bool)
    for k in sorted({c[1] for c in cand}):
        ix = np.array([i for i, c in enumerate(cand) if c[1] == k], int)
        pos = ix[np.array([cand[i][2] for i in ix], bool)]
        neg = ix[np.array([not cand[i][2] for i in ix], bool)]
        tenere[pos] = True
        if len(neg):
            quota = int(round(a.p_neg * max(len(pos), 4)))   # un minimo di negativi anche ai tasti mai premuti
            tenere[neg if quota >= len(neg) else rng.permutation(neg)[:quota]] = True
else:
    tenere = np.array([c[2] or rng.random() <= a.p_neg for c in cand], bool)
indici = sorted((i for i in range(len(cand)) if tenere[i]), key=lambda i: (cand[i][0], cand[i][1]))

# --- 3) si legge il video UNA volta e si ritaglia solo quello che si tiene ---
per_frame = collections.defaultdict(list)
for i in indici: per_frame[cand[i][0]].append(i)
X, y, ne, di, fr, no, mn = [], [], [], [], [], [], []
buf = collections.deque(maxlen=LAG + 1)
for j, f in enumerate(frames(a.video)[1]):
    if j >= n: break
    buf.append(f)
    for i in per_frame.get(j, ()):                               # i ritagli si fanno solo per i campioni tenuti
        jj, k, pos, nero, d, viste = cand[i]
        X.append(stack(f, buf[0], gr["frames"][jj]["tasti"][str(k)]["poligono"]))
        y.append(pos); ne.append(nero); di.append(d if viste else MANI_ASSENTI)
        fr.append(jj); no.append(k); mn.append(viste)
if not y:
    raise SystemExit(
        f"nessun campione utilizzabile: 0 tasti valutati, {fuori} premuti esclusi perche' lontani "
        f"dalle mani.\n  - se le mani non si vedono in --mani: togli --mani\n"
        f"  - se le note premute stanno vicine ma il raggio e' piccolo: lascia --raggio auto\n"
        f"  - controlla che --griglia e --video siano dello STESSO video (griglia.json riporta il suo)")
if int(sum(y)) == 0:
    raise SystemExit(
        f"nessun campione PREMUTO in {n} frame ({fuori} premuti scartati): un dataset di soli 'non "
        f"premuto' insegna alla rete a dire sempre no e non serve a niente.\n"
        f"  - le {len(ev)} note del MIDI non cadono sui tasti inquadrati dalla griglia, oppure il "
        f"ritardo MIDI-video e' sbagliato (guarda prima_griglia.jpg: i tasti devono stare sui tasti "
        f"veri)\n  - se il MIDI e' quello vero ma il brano usa tasti fuori inquadratura, riprendi il "
        f"video con piu' tastiera dentro")
nome = a.out or f"dataset/{Path(a.video).stem}.npz"; Path(nome).parent.mkdir(exist_ok=True)
np.savez(nome, X=np.stack(X), y=np.array(y, np.uint8), nero=np.array(ne, np.uint8),
         dist=np.array(di, np.float16), frame=np.array(fr, np.int32), nota=np.array(no, np.int16),
         mani=np.array(mn, np.uint8), fps=np.float32(fps), video=str(Path(a.video).name),
         raggio=np.float32(raggio), ritardo=np.float32(rit),
         eventi=np.array([(m, t0 + rit, t1 + rit) for m, t0, t1 in ev], np.float32).reshape(-1, 3))
conta = collections.Counter(k for k, p in zip(no, y) if p)
print(f"{nome}: {len(y)} campioni, {int(sum(y))} premuti ({100 * np.mean(y):.1f}%)")
if a.disegna:
    _img = disegna_allineamento(a.video, gr, Y, fps, n, rit, Path(nome).parent / "allineamento",
                                a.disegna)
    if _img:
        print(f"controllo dell'allineamento: {len(_img)} immagini in "
              f"{Path(nome).parent / 'allineamento'} <- i tasti che il MIDI (col ritardo "
              f"{rit:+.2f} s) dice premuti sono in rosso: devono stare sotto le dita. Se sono "
              f"spostati, il ritardo e' sbagliato (--ritardo secondi)")
    else:
        print("[!] nessuna immagine di controllo: la griglia non copre nessun frame con i tasti")
_tot_premuti = fuori + int(sum(y))
print(f"premuti ESCLUSI perche' lontani dalle mani: {fuori}"
      + (f" su {_tot_premuti} ({100 * fuori / _tot_premuti:.0f}% dei premuti)" if _tot_premuti else "")
      + "  <- con --raggio auto sono ~10% per costruzione: molto di piu' = tastiera piccola o "
        "mani lontane dai tasti premuti")
print(f"scena: {len(set(fr))} frame distinti, {len(set(no))} tasti; "
      f"premuti per tasto: mediana {int(np.median(sorted(conta.values()))) if conta else 0}, "
      f"minimo {min(conta.values()) if conta else 0}, massimo {max(conta.values()) if conta else 0}")
if a.mani:
    visti = sum(1 for m in mani if m)
    print(f"frame con le mani riconosciute: {visti}/{n} " + ("bene" if visti >= 0.8 * n else
          "ATTENZIONE: nei frame senza mani non si sa «chi preme», quindi si perdono quasi tutti "
          "(meglio un mani.json piu' completo)"))
else:
    print("frame con le mani riconosciute: nessun --mani, le dita non si usano")
if fuori and fuori > 0.2 * (fuori + int(sum(y))):
    print(f"[!] {fuori} dei premuti ({100 * fuori / (fuori + int(sum(y))):.0f}%) sono stati buttati via "
          f"dal raggio: il modello non li vedra' mai e non imparera' a riconoscerli.")
    if fuori_senza_mani:
        print(f"    ma {fuori_senza_mani} di quelli erano in frame dove le mani non si vedono: li' il "
              f"raggio non c'entra, serve un mani.json migliore (o --mani giusto per questo video).")
    if dist_fuori:
        print(f"    gli altri ({len(dist_fuori)}) stavano a distanza mediana {np.median(dist_fuori):.1f} "
              f"e nel 90% dei casi entro {np.percentile(dist_fuori, 90):.1f} larghezze dal polpastrello "
              f"piu' vicino.")
        print(f"    per tenerne il 90% basta --raggio {np.percentile(dist_fuori, 90):.1f} (con --raggio auto "
              f"lo fa da solo): 3_addestra.py legge il raggio dal dataset, cosi' addestramento e inferenza "
              f"guardano gli stessi tasti. Alzare ancora fa entrare tasti lontani e quindi piu' falsi "
              f"positivi.")
if sum(y) < 50:
    print("[!] pochissimi positivi: il dataset e' quasi tutto 'non premuto' e la rete impara a "
          "dire sempre no. Servono piu' video (o piu' note premute).")
