"""Prove rapide di comune.py: si lanciano prima di addestrare, per accorgersi subito se qualcosa
e' rotto. Non serve nessun dataset: l'unica cosa che legge da fuori e' un modello.pt vecchio,
se c'e' (per controllare che i checkpoint di prima si carichino ancora). Uso: python 0_prove.py
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comune import *   # noqa: F401,F403

radice = Path(__file__).resolve().parent
dev = device()
esiti = []

def prova(nome, cond, dettaglio=""):
    esiti.append(bool(cond))
    print(("  ok   " if cond else "  FALLITO ") + nome + (f"  [{dettaglio}]" if dettaglio else ""))

print(f"device {dev}; patch {PW}x{PH}, 6 canali in ingresso (frame attuale + frame t-{LAG}), LAG {LAG}")

# --- rete v2: avanti, con e senza i canali di movimento -------------------------------
x = torch.rand(8, 6, PH, PW, device=dev)
e = torch.rand(8, 3, device=dev)
net = Rete().to(dev)
p = net(x, e)
prova("Rete(movimento=True) produce 8 probabilita'", tuple(p.shape) == (8,), f"shape {tuple(p.shape)}")
prova("Rete(movimento=True) ha 8 canali in ingresso", net.conv[0][0].in_channels == 8)
prova("Rete(movimento=True) normalizza i 3 numeri extra", net.norm.num_features == 3)
prova("Rete(movimento=False) usa solo i 6 canali", Rete(movimento=False).conv[0][0].in_channels == 6)
prova("Rete(movimento=False) gira", tuple(Rete(movimento=False).to(dev)(x, e).shape) == (8,))
prova("mu/sigma finiscono nella rete", (net.mu, net.sigma) == (0.5, 1.0), f"{net.mu}/{net.sigma}")

# --- preprocess: patch di forma e scala giuste ----------------------------------------
xk = augmenta(x, 0.0)
prova("augmenta(0) non tocca niente", torch.equal(xk, x))
xa = augmenta(x, 1.0)
prova("augmenta conserva forma", tuple(xa.shape) == tuple(x.shape))
prova("augmenta resta in [0,1]", bool(float(xa.min()) >= 0 and float(xa.max()) <= 1.0001),
      f"{float(xa.min()):.3f}..{float(xa.max()):.3f}")
prova("augmenta cambia davvero i pixel", not torch.allclose(xa, x))

# --- lisciatura: non deve riempire i buchi (NaN = tasto non guardato) ------------------
P = np.full((12, 128), np.nan, np.float32)
P[4:8, 60] = 0.9
L = liscia(P, 3)
prova("liscia lascia NaN i tasti mai guardati", bool(np.all(np.isnan(L[:, 70]))))
prova("liscia conserva il segnale", bool(np.nanmax(L[:, 60]) > 0.5), f"max {np.nanmax(L[:, 60]):.2f}")

# --- decodifica: isteresi, durata minima, buchi ---------------------------------------
P = np.full((40, 128), np.nan, np.float32)
P[5:15, 60] = 0.9                     # nota lunga
P[9:10, 60] = 0.4                     # buco sotto la soglia di spegnimento: non chiude
P[20:21, 64] = 0.9                    # tremolio di un frame: non e' una nota
P[30:40, 67] = 0.9                   # nota che parte a meta' video (con NaN attorno)
note = decodifica(P, 10.0, 0.5, 0.35, 2)
prova("decodifica tiene la nota lunga e la chiude sull'ultimo frame visto",
      any(k == 60 and abs(t0 - 0.5) < 1e-9 and abs(t1 - 1.5) < 1e-9 for k, t0, t1, _f in note), str(note))
prova("decodifica butta la nota di un frame solo", all(k != 64 for k, *_ in note))
prova("decodifica ordina per tempo", [t for _k, t, _t1, _f in note] == sorted(t for _k, t, _t1, _f in note))
prova("decodifica ignora i tasti mai guardati", all(k != 70 for k, *_ in note))

# --- confronto note: precision, recall, errore sui tempi ------------------------------
tr = [(60, 0.20, 0.40, 6), (64, 0.70, 0.80, 21), (70, 0.90, 1.00, 27)]   # 3 riconosciute
ve = [(60, 0.19, 0.50), (64, 0.68, 0.80), (72, 0.95, 1.10)]              # 3 vere
m = confronta_note(tr, ve)
prova("confronta_note conta 2 giuste su 3 e 3", (m["n_giuste"], m["n_trovate"], m["n_vere"]) == (2, 3, 3), str(m["n_giuste"]))
prova("confronta_note: F1 0.667", abs(m["f1"] - 2 / 3) < 1e-3, f"{m['f1']:.3f}")
prova("confronta_note: una in piu' e una mancata", (m["n_extra"], m["n_mancate"]) == (1, 1))
prova("confronta_note: errore mediano sugli onset", abs(m["onset_mediano_ms"] - 15) < 1e-6,
      f"{m['onset_mediano_ms']:.1f} ms")
prova("confronta_note non esplode senza note", confronta_note([], [])["f1"] == 0.0)

# --- MIDI: andata e ritorno -----------------------------------------------------------
tmp = Path("/tmp/prove_comune.mid")
salva_midi_eventi([(60, 0.5, 1.0), (64, 1.25, 1.5)], tmp, bpm=120.0)
indietro = note_midi(tmp)
prova("MIDI scritto e riletto: stesse note", sorted(k for k, *_ in indietro) == [60, 64], str(indietro))
d = {k: a for k, a, _x in indietro}
prova("MIDI scritto e riletto: stessi tempi", all(abs(d[k] - t) < 0.003 for k, t in [(60, 0.5), (64, 1.25)]), str(d))

# --- dataset: schema nuovo e schema vecchio -------------------------------------------
for f in sorted((radice / "prova_1video" / "dataset").glob("*.npz")):
    d = np.load(f)
    print(f"  {f.name}: chiavi {sorted(d.files)} -> eventi {len(eventi_da_npz(d))}, "
          f"fps {float(d['fps']) if 'fps' in d.files else 'assenti'}")

# --- checkpoint vecchio: deve ancora caricarsi e girare --------------------------------
vecchio = radice / "prova_1video" / "modello.pt"
if vecchio.exists():
    r = carica_rete(torch.load(vecchio, map_location="cpu"), dev)
    prova("carica_rete su un .pt vecchio sceglie la rete v1", r.versione == 1, f"v{getattr(r, 'versione', '?')}")
    prova("carica_rete: il vecchio modello vuole 2 numeri extra", r.extra == 2, f"extra {r.extra}")
    q = predici_rete(r, (np.random.rand(5, 6, PH, PW) * 255).astype(np.uint8),
                     np.random.rand(5, 3).astype(np.float32), dev)   # 3 colonne: si tagliano a 2
    prova("il vecchio modello gira anche con 3 numeri extra", len(q) == 5 and bool(np.isfinite(q).all()),
          str(np.round(q, 3)))
else:
    print("  (nessun modello.pt vecchio da provare: salto quel controllo)")

# --- griglia e video: l'errore piu' rovinoso (griglia di un altro video) ---------------
vid = radice.parent / "demo_video.mp4"
if vid.exists() and (radice / "prova_1video" / "demo" / "griglia.json").exists():
    buona = carica_griglia(radice / "prova_1video" / "demo" / "griglia.json")
    prova("controlla_video accetta la griglia del video giusto",
          controlla_video(vid, buona) == int(buona["n_frame"]), f"{Path(buona['video']).name}")
    sbagliata = carica_griglia(radice / "prova_1video" / "griglia.json")
    try:
        controlla_video(vid, sbagliata)
        prova("controlla_video ferma la griglia di un altro video", False, "non ha protestato")
    except SystemExit as ex:
        prova("controlla_video ferma la griglia di un altro video",
              Path(str(sbagliata["video"])).name in str(ex), f"«{Path(sbagliata['video']).name}»")
    prova("controlla_video con forza=True lascia passare",
          controlla_video(vid, sbagliata, forza=True) == int(sbagliata["n_frame"]))
    try:
        controlla_video(vid, {"video": Path(vid).name, "n_frame": 999999})
        prova("controlla_video ferma la griglia piu' lunga del video", False, "non ha protestato")
    except SystemExit:
        prova("controlla_video ferma la griglia piu' lunga del video", True)
else:
    print("  (video/griglia non trovati: salto i controlli su controlla_video)")

# --- stima_raggio: il raggio 'auto' deve tenere il 90% dei premuti ---------------------
rng = np.random.default_rng(7)
r, avv = stima_raggio(list(rng.normal(4.2, 2.5, 4000).clip(0.2, 20)))
prova("stima_raggio mette il 90% dei premuti dentro il raggio", 3.5 <= r <= 12.0, f"raggio {r}")
prova("stima_raggio: misura pulita, nessun avviso", avv is None)
prova("stima_raggio allarga il raggio rispetto al 2.5 fisso", r > 2.5, f"{r} > 2.5")
prova("stima_raggio con pochi campioni ripiega su 2.5",
      stima_raggio([1.0, 2.0, 3.0]) == (2.5, "tasti premuti con le dita visibili troppo pochi (3) per "
                                              "misurare il raggio: uso 2.5"))
rm, avvm = stima_raggio([20.0] * 200)
prova("stima_raggio: misura assurda -> tetto 12 con avviso", (rm, avvm is not None) == (12.0, True))
prova("stima_raggio ignora i NaN", stima_raggio([np.nan] * 50)[0] == 2.5)

# --- 2_costruisci_dataset: MIDI vuoto, MIDI 'song.mid', raggio auto --------------------
mk = radice / "2_costruisci_dataset.py"
demo = radice / "prova_1video" / "demo"
if vid.exists() and (demo / "griglia.json").exists() and (demo / "mani.json").exists():
    def costruisci(midi, *extra):
        """Lancia il costruttore di dataset sul pezzo vero e ritorna il processo finito."""
        return subprocess.run([sys.executable, str(mk), "--video", str(vid),
                               "--griglia", str(demo / "griglia.json"), "--midi", str(midi),
                               "--mani", str(demo / "mani.json"), "--ritardo", "0", *extra],
                              capture_output=True, text=True, cwd=str(radice), timeout=900)
    vuoto = Path("/tmp/prove_midi_vuoto.mid"); salva_midi_eventi([], vuoto)
    npz_vuoto = Path("/tmp/prove_vuoto.npz")
    if npz_vuoto.exists(): npz_vuoto.unlink()
    e = costruisci(vuoto, "--out", str(npz_vuoto))
    prova("il costruttore rifiuta un MIDI senza note e non scrive niente",
          e.returncode != 0 and "non contiene nessuna nota" in (e.stdout + e.stderr)
          and not npz_vuoto.exists(), f"codice {e.returncode}")
    a = costruisci(demo / "song.mid", "--raggio", "auto", "--out", "/tmp/prove_auto.npz")
    _fuori = Path("/tmp/prove_out")
    if _fuori.exists():
        import shutil as _sh
        _sh.rmtree(_fuori)
    b = costruisci(demo / "song.mid", "--raggio", "2.5", "--disegna", "2",
                   "--out", str(_fuori / "fisso.npz"))
    npz_a, npz_b = Path("/tmp/prove_auto.npz"), _fuori / "fisso.npz"
    ok = a.returncode == 0 and b.returncode == 0 and npz_a.exists() and npz_b.exists()
    prova("il costruttore gira con --raggio auto e con un numero", ok,
          f"codici {a.returncode}/{b.returncode}")
    if ok:
        da, db = np.load(npz_a), np.load(npz_b)
        pa, pb = int(da["y"].sum()), int(db["y"].sum())
        prova("raggio auto tiene molti piu' tasti premuti di 2.5", pa > 1.3 * pb, f"{pa} contro {pb}")
        prova("il dataset ricorda raggio e ritardo usati",
              "raggio" in da.files and "ritardo" in da.files,
              f"raggio {float(da['raggio']):.1f}, ritardo {float(da['ritardo']):+.3f} s")
        prova("il dataset ricorda da quale video viene", Path(str(da["video"])).name == vid.name,
              str(da["video"]))
        prova("l'avviso sul MIDI 'song.mid' arriva nel log", "song.mid" in (a.stdout + a.stderr))
        # --- controllo dell'allineamento a occhio (--disegna): immagini coi tasti premuti -----
        _img = sorted((_fuori / "allineamento").glob("*.jpg"))
        prova("--disegna salva le immagini di controllo", len(_img) == 2,
              ", ".join(x.name for x in _img))
        prova("le immagini di controllo non sono vuote",
              all(x.stat().st_size > 2000 for x in _img),
              ", ".join(f"{x.name} {x.stat().st_size // 1024} kB" for x in _img))
        prova("il log spiega a cosa servono le immagini",
              "devono stare sotto le dita" in (b.stdout + b.stderr))
else:
    print("  (video o mani non trovati: salto i controlli su 2_costruisci_dataset)")

# --- disegna_allineamento: quando non c'e' niente da disegnare non deve rompersi "--------------
_gr_vuota = {"frames": [{"tasti": {}}, {"tasti": {}}]}
prova("disegna_allineamento senza tasti non scrive niente",
      disegna_allineamento("/tmp/non_esiste.mp4", _gr_vuota, np.zeros((2, 128), bool), 10.0, 2,
                           0.0, Path("/tmp/prove_senza_tasti")) == [])
_gr = {"frames": [{"tasti": {"60": {"poligono": [[0, 0], [4, 0], [4, 4], [0, 4]]}}},
                  {"tasti": {"60": {"poligono": [[0, 0], [4, 0], [4, 4], [0, 4]]}}}]}
prova("disegna_allineamento con un video illeggibile non esplode",
      disegna_allineamento("/tmp/non_esiste.mp4", _gr, np.ones((2, 128), bool), 10.0, 2, 0.25,
                           Path("/tmp/prove_video_rotto")) == [])

# --- le interfacce si aprono: un help malformato ferma tutto prima di iniziare ---------
for _s in ("1_estrai_mani.py", "2_costruisci_dataset.py", "3_addestra.py", "4_inferenza.py", "5_valuta.py"):
    _f = radice / _s
    if not _f.exists():
        continue
    _h = subprocess.run([sys.executable, str(_f), "--help"], capture_output=True, text=True, timeout=120)
    prova(f"--help di {_s} non esplode", _h.returncode == 0,
          f"codice {_h.returncode} {(_h.stderr or '').strip().splitlines()[-1] if _h.returncode else ''}")

# --- il controllo dell'allineamento nel sito: pagina e server devono restare agganciati -------
_pag, _srv = radice.parent / "pipeline_studio.html", radice.parent / "pipeline_web.py"
if _pag.is_file() and _srv.is_file():
    _html, _web = _pag.read_text(encoding="utf-8"), _srv.read_text(encoding="utf-8")
    _aiuto = subprocess.run([sys.executable, str(mk), "--help"], capture_output=True,
                            text=True, timeout=120).stdout
    prova("il costruttore ha --disegna (immagini di controllo)", "--disegna" in _aiuto)
    prova("la pagina ha un campo di scostamento per ogni pezzo",
          "allinea__" in _html and "input.allinea" in _html)
    prova("la pagina manda lo scostamento di ogni pezzo al server",
          "fd.append('allinea__' + n" in _html)
    prova("la pagina ha il pulsante «Controlla l'allineamento»", "controllaAllinea" in _html)
    prova("la pagina mostra le immagini di controllo", "immaginiAllineamento" in _html)
    prova("la pagina riusa il corso preparato quando si addestra", "riusaCorso" in _html)
    prova("il server legge lo scostamento pezzo per pezzo", 'f"allinea__{s}"' in _web)
    prova("il server usa il ritardo del pezzo (non uno solo per tutti)",
          "rit_pezzo = allineamenti.get(stem)" in _web)
    prova("il server riusa griglia e dita se ci sono gia'",
          "riuso la griglia gia' calcolata" in _web and "riuso le dita gia' estratte" in _web)
    prova("il server sa fare il corso 'solo controllo allineamento'",
          'p.get("prepara")' in _web and "NON ho addestrato" in _web)
    prova("il server legge il corso da riusare", 'request.form.get("riusa")' in _web)
    prova("il riepilogo modello.json porta i ritardi usati",
          "ritardo_midi_per_pezzo" in _web)
    prova("un caricamento oltre il limite risponde in JSON (messaggio leggibile)",
          "@app.errorhandler(413)" in _web and "carica meno pezzi" in _web)
    prova("la pagina legge l'errore anche quando la risposta non e' JSON",
          "caricamento rifiutato (HTTP" in _html)
else:
    print("  (pipeline_studio.html/pipeline_web.py non trovati: salto i controlli sul sito)")

# --- il verdetto del passo 0: un primo piano NON e' una griglia sbagliata ----------------------
# Numeri veri di un primo piano dell'utente (720x386 sulla parte sinistra di una tastiera): la
# finestra mostra 13,7 tasti bianchi e 36,8 tasti del modello restano fuori dal ritaglio, ma la
# griglia sta sui tasti (58 inlier, passo a -0,9% dal profilo, etichette da MI2 a DO4 sui tasti
# veri). Prima del 05/10/2026 il verdetto diceva "incerto" perche' la finestra veniva confrontata
# con i 52 tasti della tastiera intera: su un fotogramma stretto quei due numeri sono la geometria
# del fotogramma, non un difetto.
_prep = radice / "0_prepara.py"
if _prep.is_file():
    import importlib.util
    _spec = importlib.util.spec_from_file_location("prep0", _prep)
    prep0 = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(prep0)

    def numeri(**kw):
        d = {"inlier": 58, "passo": 52.44, "evidenza": 0.664, "tasti_nel_frame": 13.7,
             "tasti_fuori": 36.8, "H": None}
        d.update(kw)
        return d

    v, perche = prep0.verdetto(numeri(), 52.9)
    prova("primo piano (14 tasti nella finestra, 36,8 fuori) -> ok", v == "ok", f"{v}: {perche}")
    prova("e la ragione dice che e' un primo piano", "primo piano" in perche, perche)
    v, perche = prep0.verdetto(numeri(), 52.9, auto=False)
    prova("primo piano col rettangolo a mano -> ok", v == "ok", f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(inlier=30), 52.9)
    prova("primo piano ma solo 30 inlier -> rifiuto", v == "rifiuto", f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(passo=56.6), 52.9)
    prova("primo piano col passo a +7% dal profilo -> rifiuto", v == "rifiuto", f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(evidenza=0.50), 52.9)
    prova("primo piano poco plausibile (0.50) -> incerto", v == "incerto", f"{v}: {perche}")

    # Un profilo che NON legge non puo' decretare un rifiuto. Numeri veri del run
    # `web_runs/_prepara/a662e8fa2ce5425f/video5906842636420915152_preparato.json`: tastiera
    # ruotata (~10 px per tasto veri, misurati sui neri), il profilo diceva 76,4 px (= 11 tasti
    # nel fotogramma, dove si vede la tastiera intera da 52) con NCC 0,372, e la griglia "intero"
    # col passo a 10,17 px (193 inlier, 0,61 di plausibilita') veniva RIFIUTATA. Prima del
    # 05/10/2026 il video preparato non si scriveva affatto.
    v, perche = prep0.verdetto(numeri(inlier=193, passo=10.17, evidenza=0.608,
                                      tasti_nel_frame=83.4, tasti_fuori=0.0), 76.43,
                               ncc_profilo=0.372)
    prova("profilo illeggibile (NCC 0,372): passo 10,2 vs 76,4 -> incerto, non rifiuto",
          v == "incerto" and "tasti bianchi nella finestra" in perche, f"{v}: {perche}")
    # La ragione che si legge e' quella dei tasti di troppo ("83 tasti bianchi nella finestra", e
    # una tastiera ne ha 52): e' il difetto che si vede nel controllo, e dal 09/10/2026 il controllo
    # sui tasti viene PRIMA di quello sul profilo, quindi e' lei a essere mostrata. Che un profilo
    # illeggibile non decreti il rifiuto resta verificato dalla riga qui sopra (il livello) e da
    # quella qui sotto, dove i tasti sono plausibili (52) e la ragione torna quella del profilo.
    v, perche = prep0.verdetto(numeri(inlier=226, passo=10.17, evidenza=0.608,
                                      tasti_nel_frame=52.0, tasti_fuori=0.0), 76.43,
                               ncc_profilo=0.372)
    prova("coi tasti plausibili (52) la ragione torna quella del profilo illeggibile",
          v == "incerto" and "profilo non legge" in perche, f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(inlier=193, passo=10.17, evidenza=0.608,
                                      tasti_nel_frame=83.4, tasti_fuori=0.0), 76.43)
    prova("gli stessi numeri senza la NCC del profilo restano un rifiuto",
          v == "rifiuto" and "non è coerente" in perche, f"{v}: {perche}")

    # IL SECONDO PARERE QUANDO IL PROFILO NON LEGGE (10/10/2026). Numeri veri dell'esempio 69
    # (`2024-09-02_20-00-16`, pianoforte FERMO): il profilo diceva 115,3 px = 4,3 tasti contro i
    # 27,0 veri, con NCC 0,31, e il verdetto restava "incerto" per quella sola ragione, mentre la
    # griglia sta sui tasti (154 inlier, 0,78 di plausibilità, 0 px di scarto agli estremi, 0 tasti
    # fuori) e i tasti misurati uno per uno su tutto il video la confermano: 85 misure coerenti su
    # 87, 2 incoerenti, 4 sotto le mani ipotizzate, escursione 0 tasti.
    _es69 = dict(inlier=154, passo=27.02, evidenza=0.782, tasti_nel_frame=52.3, tasti_fuori=0.0,
                 ancorata=True, tasti_fuori_dalla_tastiera=0.0,
                 tasti_misurati={"misurati": 85, "incoerenti": 2, "ipotizzati": 4,
                                 "escursione_tasti": 0})
    v, perche = prep0.verdetto(numeri(**_es69), 115.27, ncc_profilo=0.308)
    prova("profilo illeggibile ma tasti misurati coerenti (esempio 69) -> ok", v == "ok",
          f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(**{**_es69, "ancorata": False}), 115.27, ncc_profilo=0.308)
    prova("gli stessi numeri SENZA ancoraggio: il profilo resta l'unico parere -> incerto",
          v == "incerto" and "profilo non legge" in perche, f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(**{**_es69, "tasti_misurati": None}), 115.27, ncc_profilo=0.308)
    prova("senza le misure dei tasti il secondo parere non c'e' -> incerto",
          v == "incerto" and "profilo non legge" in perche, f"{v}: {perche}")
    # Le stesse misure ma con la griglia che NON sta sui tasti: 20 misure fuori dal consenso su 65
    # (l'esempio 9, `2024-02-15_20-07-54`, ne ha 20 su 65) non confermano niente.
    _tm = {"misurati": 65, "incoerenti": 20, "ipotizzati": 24, "escursione_tasti": 1}
    v, perche = prep0.verdetto(numeri(**{**_es69, "tasti_misurati": _tm}), 115.27, ncc_profilo=0.308)
    prova("tasti misurati ma un terzo fuori dal consenso -> incerto",
          v == "incerto" and "profilo non legge" in perche, f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(**{**_es69, "tasti_misurati":
                                         {"misurati": 30, "incoerenti": 1, "ipotizzati": 4,
                                          "escursione_tasti": 0}}), 115.27, ncc_profilo=0.308)
    prova("troppo poche misure (30) per dire che la griglia sta sui tasti -> incerto",
          v == "incerto" and "profilo non legge" in perche, f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(**{**_es69, "tasti_misurati":
                                         {"misurati": 85, "incoerenti": 2, "ipotizzati": 4,
                                          "escursione_tasti": 2}}), 115.27, ncc_profilo=0.308)
    prova("griglia che scorre di 2 tasti fra i due capi -> incerto",
          v == "incerto" and "profilo non legge" in perche, f"{v}: {perche}")
    # L'altra ripresa col profilo che non legge e la griglia ancorata giusta: `2024-02-15_21-40-43`,
    # profilo 166,2 px (= 5 tasti nel fotogramma dove ne entrano 52) con NCC 0,33, griglia a 33,1 px
    # (la verità del dataset è 33,12), 92 inlier e 0,73 di plausibilità.
    v, perche = prep0.verdetto(numeri(inlier=92, passo=33.1, evidenza=0.733, tasti_nel_frame=52.3,
                                      tasti_fuori=0.0, ancorata=True,
                                      tasti_fuori_dalla_tastiera=0.0,
                                      tasti_misurati={"misurati": 75, "incoerenti": 2,
                                                      "ipotizzati": 14, "escursione_tasti": 1}),
                               166.17, ncc_profilo=0.327)
    prova("profilo a 166 px su una tastiera intera inquadrata -> ok (tasti misurati)",
          v == "ok", f"{v}: {perche}")
    prova("_tasti_misurati_ok: serve l'ancoraggio e le misure",
          prep0._tasti_misurati_ok(_es69) and not prep0._tasti_misurati_ok({**_es69, "ancorata": False})
          and not prep0._tasti_misurati_ok({**_es69, "tasti_misurati": None}),
          "ancorata + 85 misure coerenti")
    v, perche = prep0.verdetto(numeri(inlier=226, passo=33.43, evidenza=0.70,
                                      tasti_nel_frame=52.0, tasti_fuori=0.0), 33.12,
                               ncc_profilo=0.372)
    prova("col profilo illeggibile un passo coerente resta ok", v == "ok", f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(inlier=226, passo=33.6, evidenza=0.70,
                                      tasti_nel_frame=52.0, tasti_fuori=0.0), 33.12,
                               ncc_profilo=0.372)
    prova("col profilo illeggibile uno scarto piccolo non fa piu' 'incerto'",
          v == "ok", f"{v}: {perche}")

    # LA TASTIERA INTERA MISURATA A UN TASTO DI MENO (10/10/2026). Numeri veri dell'esempio 66
    # (`2024-09-02_18-29-40`, tastiera intera inquadrata): la fascia misurata su tutto il pezzo
    # dava LA0 249 px e DO8 1650 (contro 243 e 1671 veri, passo 27,5 contro 28,0, copertura 100%)
    # con 31 neri letti, ma il conteggio usciva 51 perche' l'ULTIMO tasto e' in ombra. Col confronto
    # `tasti == 52` quella misura veniva buttata via, `estremi` non esisteva e il centraggio delle 88
    # note spostava la griglia di 13 tasti (2 ottave) a destra: riquadri sui tasti ma nomi sbagliati
    # e la prima ottava e mezza senza griglia. 51 tasti bianchi non esistono (88 tasti -> 52 bianchi,
    # 76 -> 45, 61 -> 36, 49 -> 29): e' la tastiera intera con un tasto perso dalla misura.
    _est66 = {"x_la0": 249.0, "x_c8": 1650.0, "passo": 27.47, "copertura": 1.0, "tasti": 51,
              "campioni": 12, "neri_misurati": 31}
    prova("_tastiera_intera: 51 tasti misurati (esempio 66) valgono come la tastiera intera",
          prep0._tastiera_intera(_est66), f"LA0 {_est66['x_la0']:.0f}, DO8 {_est66['x_c8']:.0f}")
    prova("_tastiera_intera: 52 tasti (misura piena) restano la tastiera intera",
          prep0._tastiera_intera({**_est66, "tasti": 52}))
    prova("_tastiera_intera: 50 tasti non bastano (due persi: la misura non e' piu' sicura)",
          not prep0._tastiera_intera({**_est66, "tasti": 50}))
    prova("_tastiera_intera: 53 tasti sono un tasto fantasma letto fuori dalla tastiera",
          not prep0._tastiera_intera({**_est66, "tasti": 53}))
    prova("_tastiera_intera: 45 bianchi (un 76 tasti) non e' la tastiera intera",
          not prep0._tastiera_intera({**_est66, "tasti": 45}))
    prova("_tastiera_intera: senza la misura non c'e' nessuna tastiera intera",
          not prep0._tastiera_intera(None) and not prep0._tastiera_intera({}))

    # La finestra che la tastiera la puo' contenere continua a essere controllata.
    v, perche = prep0.verdetto(numeri(inlier=226, passo=33.43, evidenza=0.70,
                                      tasti_nel_frame=59.2, tasti_fuori=0.0), 33.12)
    prova("finestra piu' larga della tastiera (59,2 tasti) -> incerto",
          v == "incerto" and "tasti bianchi nella finestra" in perche, f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(inlier=200, passo=33.2, evidenza=0.70,
                                      tasti_nel_frame=52.0, tasti_fuori=2.0), 33.12)
    prova("griglia scivolata di 2 tasti su una finestra larga quanto la tastiera -> incerto",
          v == "incerto" and "fuori" in perche, f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(inlier=231, passo=33.15, evidenza=0.60, ancorata=True,
                                      tasti_nel_frame=52.3, tasti_fuori=0.1,
                                      tasti_fuori_dalla_tastiera=0.0), 33.43)
    prova("candidato ancorato agli estremi (52,3 tasti, 0,1 fuori) -> ok", v == "ok",
          f"{v}: {perche}")
    v, perche = prep0.verdetto(numeri(inlier=231, passo=33.15, evidenza=0.60, ancorata=True,
                                      tasti_nel_frame=52.3, tasti_fuori=0.1,
                                      tasti_fuori_dalla_tastiera=2.0), 33.43)
    prova("griglia che esce dalla tastiera misurata di 2 tasti -> incerto",
          v == "incerto" and "esce dalla tastiera" in perche, f"{v}: {perche}")

    # Il caso RITAGLIATO IN ALTO (il video a mano libera dell'utente, 848x464): il taglio porta
    # via le righe in cui il blocco dei neri si sta formando, cosi' la riga di misura di sempre
    # (y0+25) finisce nella CODA del blocco, dove il capo sinistro della tastiera e' in ombra e i
    # neri non si leggono piu' (i tratti scuri si allargano oltre la larghezza di un tasto). Su
    # quel fotogramma l'ancora contava 31 neri su 41, il centro dello span andava 93 px a destra
    # (386 -> 479) e il gruppo da due neri scelto era C#5-D#5 invece di C#4-D#4: la griglia usciva
    # 7 tasti a destra (misurato: primo nero disegnato a 212 px invece di 139,5). La riga PIENA
    # serve solo a scegliere l'OTTAVA: le righe di misura restano quelle di sempre, altrimenti
    # cambierebbe la geometria per tutti i video.
    import cv2
    _img = np.full((342, 848, 3), 255, np.uint8)
    for _k in range(41):                              # i neri veri: passo 10,17 px, larghi 7 px
        _x = int(round(139.5 + 10.17 * _k))
        _img[47:84, _x - 3:_x + 4] = 0
    _y0, _ya, _yb, _pieno, _leggi = prep0.G.banda_neri(_img)
    prova("neri: le righe di misura restano y0+25 e il 55% del blocco", _ya - _y0 == 25,
          f"y0 {_y0}, ya {_ya}, yb {_yb}")
    prova("fotogramma intero (nessuna ombra): riga di sempre piena, nessun cambio di misura",
          _pieno is None and len(_leggi(_ya)) == 41, f"pieno {_pieno}, {len(_leggi(_ya))} neri")
    _img[74:84, :300] = 0                             # il capo sinistro in ombra: i neri si allargano
    _y0, _ya, _yb, _pieno, _leggi = prep0.G.banda_neri(_img)
    prova("ritaglio in alto, riga di sempre in ombra: si legge la riga PIENA per l'ottava",
          _pieno is not None and len(_leggi(_ya)) < 41 and len(_leggi(_pieno)) == 41,
          f"ya {_ya}: {len(_leggi(_ya))} neri; piena {_pieno}: {len(_leggi(_pieno))} neri")
    prova("nessun nero nel fotogramma -> banda dei neri assente, senza errori",
          prep0.banda_dai_neri(np.full((342, 848, 3), 255, np.uint8)) is None)

    # --- avvio cieco: il primo fotogramma non e' una tastiera ------------------------------------
    # Un clip che comincia con la mano (col telefono davanti ai tasti) non deve restare "70,6 tasti
    # bianchi nella finestra": `avvio_utile` sposta l'inizio sul primo fotogramma che LEGGE. Qui il
    # fotogramma lo disegna il renderer del progetto (`_render_modello`, profilo NCC 0,91) e la
    # "mano" e' un rettangolo scuro che sul fotogramma di partenza lo copre (NCC 0,30, sotto
    # `_NCC_PROFILO_MIN`), come sul primo fotogramma di `2024-02-15_21-33-36` (NCC 0,32 misurato).
    # Nessun file su disco: il video e' un finto VideoCapture con 20 fotogrammi coperti (0,67 s) e
    # 40 buoni, a 30 fps.
    _Hp = np.array([[33.0, 0.0, 100.0], [0.0, 33.0, 60.0], [0.0, 0.0, 1.0]])
    _pulito = cv2.cvtColor(prep0._render_modello(_Hp, (342, 848))[0], cv2.COLOR_GRAY2BGR)
    _coperto = _pulito.copy()
    cv2.rectangle(_coperto, (100, 60), (800, 342), (10, 10, 10), -1)
    _ncc0 = prep0.G.passo_profilo(_coperto)
    _ncc0 = float(_ncc0[2]) if _ncc0 is not None else 0.0
    prova("avvio: il fotogramma di partenza di prova non legge (NCC sotto la soglia)",
          _ncc0 < prep0._NCC_PROFILO_MIN, f"NCC {_ncc0:.2f}")

    class _CapFinto:
        def __init__(self, fotogrammi):
            self.f, self.i = fotogrammi, 0

        def set(self, prop, v):
            if prop == cv2.CAP_PROP_POS_FRAMES:
                self.i = int(v)

        def read(self):
            if self.i >= len(self.f):
                return False, None
            x = self.f[self.i]
            self.i += 1
            return True, x

        def grab(self):
            # Come `read`, ma senza il fotogramma: sono i fotogrammi che il controllo SALTA (`passo`),
            # e devono avanzare lo stesso, altrimenti il pezzo non finirebbe mai.
            if self.i >= len(self.f):
                return False
            self.i += 1
            return True

        def release(self):
            pass

    _vero_apri = prep0.apri
    prep0.apri = lambda v: (_CapFinto([_coperto] * 20 + [_pulito] * 40), 30.0, 60)
    try:
        _in, _fr, _nota = prep0.avvio_utile("finto.mp4", 0.0, 0.0, _coperto)
        _in2, _fr2, _nota2 = prep0.avvio_utile("finto.mp4", 1.0, 0.0, _pulito)
    finally:
        prep0.apri = _vero_apri
    _nccf = prep0.G.passo_profilo(_fr)[2]
    prova("avvio cieco: l'inizio si sposta sul primo fotogramma che legge",
          _in > 0 and _fr is not _coperto and _nccf >= prep0._NCC_PROFILO_MIN,
          f"inizio {_in:.1f} s, NCC {_nccf:.2f}")
    prova("avvio cieco: la ragione dice che il primo fotogramma non legge",
          _nota is not None and "non legge" in _nota, str(_nota))
    prova("avvio che legge: inizio e fotogramma non si toccano, nessuna nota",
          _in2 == 1.0 and _fr2 is _pulito and _nota2 is None, f"inizio {_in2}, nota {_nota2}")

    # Il fotogramma NERO (la camera che si accende) non e' nemmeno un'ancora: `passo_profilo` non da'
    # nessun passo e i neri non ci sono, quindi `candidati_auto` li' si arrende ("in questo video non
    # trovo nessuna periodicita' di tasti"). E' il caso dell'esempio 83 della pagina
    # (2024-09-04_20-09-07, 1920x1080): fotogramma 0 nero (luminanza 0), poi il profilo legge il passo
    # VERO -- 27,35 px contro i 27,08 della tastiera misurata su tutto il pezzo -- ma con NCC 0,37-0,40,
    # sotto la soglia 0,45 per TUTTI i 1800 fotogrammi. Quando nessuno legge l'inizio deve andare sul
    # primo fotogramma che almeno FA DA ANCORA (`ancora_utile`); e se quello di partenza e' gia' un'ancora
    # (il caso obliquo, dove il profilo legge male ma il passo 0 ci sa lavorare) non si sposta niente.
    _nero = np.zeros((342, 848, 3), np.uint8)
    _meta = _pulito.copy()
    cv2.rectangle(_meta, (0, 0), (600, 342), (10, 10, 10), -1)     # mano/ombra su un terzo dei tasti
    _pm = prep0.G.passo_profilo(_meta)
    _nccm = float(_pm[2]) if _pm is not None else 0.0
    prova("avvio: il fotogramma 'letto male' della prova ha un passo ma NCC sotto la soglia",
          _pm is not None and _nccm < prep0._NCC_PROFILO_MIN, f"passo {_pm[0]:.2f}, NCC {_nccm:.2f}")
    prova("ancora: chi non legge ma ha il passo del profilo E' un'ancora",
          prep0.ancora_utile(_meta, _pm) is True)
    prova("ancora: il fotogramma nero e la tastiera coperta non sono ancore",
          prep0.ancora_utile(_nero, prep0.G.passo_profilo(_nero)) is False
          and prep0.ancora_utile(_coperto, None) is False)

    prep0.apri = lambda v: (_CapFinto([_nero] * 10 + [_meta] * 50), 30.0, 60)
    try:
        _in3, _fr3, _nota3 = prep0.avvio_utile("finto2.mp4", 0.0, 0.0, _nero)
        _ncc3 = float(prep0.G.passo_profilo(_fr3)[2])
    finally:
        prep0.apri = _vero_apri
    prova("avvio cieco: il fotogramma di partenza nero si lascia al primo che fa da ancora",
          _in3 == 0.5 and _fr3 is not _nero and _nota3 is not None and "non legge" in _nota3,
          f"inizio {_in3:.1f} s, NCC {_ncc3:.2f}")
    prova("avvio cieco: il fotogramma-ancora scelto NON legge (si e' accettato il minimo)",
          _ncc3 < prep0._NCC_PROFILO_MIN, f"NCC {_ncc3:.2f}")

    prep0.apri = lambda v: (_CapFinto([_meta] * 60), 30.0, 60)
    try:
        _in4, _fr4, _nota4 = prep0.avvio_utile("finto3.mp4", 0.0, 0.0, _meta)
    finally:
        prep0.apri = _vero_apri
    prova("avvio: se il fotogramma di partenza e' gia' un'ancora l'inizio non si sposta",
          _in4 == 0.0 and _fr4 is _meta and _nota4 is None, f"inizio {_in4:.1f}, nota {_nota4}")

    # --- i 4 angoli dei tasti bianchi: la tastiera sta ferma o si muove? --------------------------
    # E' il controllo che ACCENDE l'inseguimento (`tastiera_ferma`, chiamata da `main` con
    # `--insegui auto`): se i 4 angoli della griglia VERDE -- il blocco dei tasti bianchi, non il
    # rettangolo magenta del ritaglio -- non si spostano su tutto il pezzo, il passo 0 resta col
    # ritaglio e la griglia del primo fotogramma, senza inseguire niente. Qui i fotogrammi li
    # disegna il renderer del progetto (`_render_modello`) e il video e' un `_CapFinto`, come nei
    # controlli qui sopra: nessun file su disco.
    def _fotogramma(dx=0.0):
        Hu = _Hp.copy()
        Hu[0, 2] += dx            # la tastiera si sposta nella scena (e' la camera che si muove)
        return cv2.cvtColor(prep0._render_modello(Hu, (342, 848))[0], cv2.COLOR_GRAY2BGR)

    def _ferma(fotogrammi):
        prep0.apri = lambda v: (_CapFinto(fotogrammi), 30.0, len(fotogrammi))
        try:
            return prep0.tastiera_ferma("finto.mp4", (0, 0, 848, 342), _Hp, 0.0, 0.0)
        finally:
            prep0.apri = _vero_apri

    # I 4 angoli sono davvero gli angoli ESTERNI della griglia verde: il rettangolo che li contiene
    # e' lo stesso che contiene TUTTI i riquadri verdi dei tasti bianchi (quelli che si vedono
    # disegnati), non il rettangolo magenta del ritaglio ne' la banda con margine.
    _verdi = np.vstack([prep0.G.poligono_tasto(_Hp, n) for n in prep0.G.BIANCHI]).astype(float)
    _ang = prep0.angoli_bianchi(_Hp)
    prova("i 4 angoli sono gli angoli esterni dei riquadri verdi dei tasti bianchi",
          np.allclose(_ang[:, 0].min(), _verdi[:, 0].min(), atol=0.5)
          and np.allclose(_ang[:, 0].max(), _verdi[:, 0].max(), atol=0.5)
          and np.allclose(_ang[:, 1].min(), _verdi[:, 1].min(), atol=0.5)
          and np.allclose(_ang[:, 1].max(), _verdi[:, 1].max(), atol=0.5),
          f"angoli x {_ang[:, 0].min():.0f}..{_ang[:, 0].max():.0f} contro i riquadri verdi "
          f"x {_verdi[:, 0].min():.0f}..{_verdi[:, 0].max():.0f}")

    _fermo_f = _fotogramma(0.0)
    _f, _n = _ferma([_fermo_f] * 120)
    # `campioni` conta i fotogrammi GUARDATI (uno ogni `_PASSO_ANGOLI`): e' quello che tiene basso il
    # costo del controllo, e va verificato qui, altrimenti un passo tornato a 1 non se ne accorgerebbe.
    prova("4 angoli fermi su tutto il video -> nessun inseguimento",
          (_f is True and _n["decisa"] == "ferma" and _n["x_max_px"] < 1.0
           and _n["campioni"] <= 1 + _n["frame"] // prep0._PASSO_ANGOLI),
          f"{_n['decisa']}: {_n['x_max_px']} px in x, {_n['y_max_px']} px in y, "
          f"{_n['misurabili']}/{_n['campioni']} campioni misurati su {_n['frame']} fotogrammi "
          f"(uno ogni {_n['passo']})")

    _toll = prep0._TOLLERANZA_ANGOLI_PX
    _f, _n = _ferma([_fermo_f] * 60 + [_fotogramma(_toll + 6.0)] * 60)
    prova("tastiera che si sposta OLTRE la tolleranza a meta' pezzo -> inseguimento, dal fotogramma giusto",
          _f is False and _n["decisa"] == "si muove" and 60 <= _n["primo_fuori"] <= 63
          and _n["fuori"] > prep0._ANGOLI_FUORI_MAX,
          f"{_n['decisa']} dal fotogramma {_n['primo_fuori']} di {_n['frame']} "
          f"({_n['fuori']} fotogrammi fuori tolleranza)")

    _f, _n = _ferma([_fermo_f] * 20 + [_fotogramma(1.0)] * 20)
    prova(f"spostamento di 1 px (sotto la tolleranza di {_toll:.0f} px) -> ancora ferma",
          _f is True and _n["decisa"] == "ferma", f"{_n['x_max_px']} px in x")

    # UN FOTOGRAMMA STORTO DA SOLO NON E' MOVIMENTO: era la trappola che faceva dire "si muove" al
    # video intero di `2024-02-15_21-33-36` (2,7 px in x su un fotogramma) e a
    # `2024-09-02_20-00-16` (5,9 px in y al fotogramma 15) mentre l'inseguimento, su quegli stessi
    # pezzi, misurava 0,04 e 0,21 tasti e concludeva "la camera sta ferma". Il margine che li perdona
    # e' `_ANGOLI_FUORI_MAX` fotogrammi; sopra quel margine la tastiera si muove davvero.
    # Lo storto deve restare MISURABILE: oltre ~20 px la registrazione non aggancia piu' il
    # fotogramma e lo conta fra gli illeggibili (`_registra` salta), quindi 14 px -- come nello
    # spostamento vero qui sopra -- e' il fotogramma storto tipico: misurato, oltre tolleranza, solo.
    _spike = [_fotogramma(_toll + 6.0)]
    _f, _n = _ferma([_fermo_f] * 60 + _spike + [_fermo_f] * 59)
    prova("un fotogramma storto da solo (mano sui bordi, registrazione andata male) non fa \"si muove\"",
          _f is True and _n["decisa"] == "ferma" and _n["fuori"] == 1 and _n["x_max_px"] > _toll,
          f"{_n['decisa']}: {_n['fuori']} fotogramma fuori tolleranza, massimo {_n['x_max_px']} px in x")

    # QUATTRO FOTOGRAMMI STORTI SPARSI NON SONO MOVIMENTO, e contare il TOTALE li scambiava per tale:
    # su `2024-09-02_20-00-16` (il pianoforte FERMO dell'esempio 69, il caso vero che ha aperto questa
    # prova: 285 fotogrammi, 143 campioni, 4 storti sparsi, 11,2 px in x contro una soglia di 8) il
    # totale 4 superava il margine di 3, l'inseguimento si accendeva e la griglia inseguita si metteva
    # a traballare (scarto in y fino a 12 px al secondo 49), mentre l'inseguimento stesso misurava
    # 0,2 tasti e concludeva "la camera sta ferma". Qui i 4 fotogrammi storti (14 px) stanno a 40, 90,
    # 150 e 220 su 285: distanti fra loro, mai due di fila, come sul pezzo vero (i campioni guardati
    # sono i fotogrammi pari, quindi gli storti vanno messi su indici pari perche' li veda).
    def _con_storti(indici, quanti=285):
        f = [_fermo_f] * quanti
        for i in indici:
            f[i] = _fotogramma(_toll + 6.0)
        return f

    _f, _n = _ferma(_con_storti([40, 90, 150, 220]))
    prova("quattro fotogrammi storti SPARSI su tutto il pezzo non accendono l'inseguimento",
          _f is True and _n["decisa"] == "ferma" and _n["fuori"] == 4 and _n["di_fila_max"] == 1
          and _n["x_max_px"] > _toll,
          f"{_n['decisa']}: {_n['fuori']} storti su {_n['campioni']} campioni, al massimo "
          f"{_n['di_fila_max']} di fila, {_n['x_max_px']} px in x")

    # Il controllo guarda un campione ogni `_PASSO_ANGOLI` fotogrammi (per non pagare il doppio del
    # tempo: vedi le costanti di `0_prepara.py`), quindi gli storti vanno messi su fotogrammi che
    # vengono GUARDATI: due volte il margine, cosi' i campioni storti superano il margine qualunque
    # sia il passo (con passo 2 sono `_ANGOLI_FUORI_MAX + 1` campioni su 8 fotogrammi). E devono
    # essere CONSECUTIVI: da questa correzione il movimento lo fa la FILA di campioni storti, non il
    # loro totale (la prova qui sopra ha gli stessi 4 campioni, ma sparsi, e non basta).
    _f, _n = _ferma([_fermo_f] * 60 + _spike * (2 * (prep0._ANGOLI_FUORI_MAX + 1)) + [_fermo_f] * 52)
    prova(f"{prep0._ANGOLI_FUORI_MAX + 1} campioni storti di fila (sopra il margine) -> inseguimento",
          _f is False and _n["decisa"] == "si muove",
          f"{_n['decisa']}: {_n['fuori']} campioni fuori tolleranza su {_n['campioni']}")

    # UNA COSTANTE SBAGLIATA NON DEVE POTER DIRE "FERMA": il 10/10/2026 `_ANGOLI_FUORI_MAX` e' rimasto
    # a 100000 (un valore di prova) e un pezzo di telefonino che si muove di 779 px e' stato dichiarato
    # fermo, con la griglia del fotogramma 0 inchiodata addosso per tutto il video (MIDI sbagliato).
    # Il margine in fotogrammi si puo' sbagliare; la frazione no: se quasi meta' dei campioni sta fuori
    # tolleranza, la tastiera si muove (o il pezzo non si misura) e si insegue.
    _max_vero = prep0._ANGOLI_FUORI_MAX
    prep0._ANGOLI_FUORI_MAX = 100000
    try:
        _f, _n = _ferma([_fermo_f] * 20 + [_fotogramma(_toll + 6.0)] * 20)
    finally:
        prep0._ANGOLI_FUORI_MAX = _max_vero
    prova("un margine di perdonanza assurdo non puo' far dire \"ferma\" a un pezzo che si muove",
          _f is False and _n["decisa"] == "si muove",
          f"{_n['decisa']}: {_n['fuori']} campioni fuori tolleranza su {_n['campioni']} "
          f"(perdonanza {_n['fuori_max']}, frazione {_n['fuori_frazione_max']})")

    _rng = np.random.default_rng(3)
    _f, _n = _ferma([_rng.integers(0, 60, (342, 848, 3), dtype=np.uint8) for _ in range(40)])
    prova("fotogrammi illeggibili (rumore) non dicono 'ferma'", _f is not True,
          f"{_n.get('decisa')}: {_n.get('misurabili')}/{_n.get('campioni')} campioni misurati")

    # --- il moto inseguito si butta quando non si vede (`_moto_angoli`) ---------------------------
    # E' la seconda porta della stessa regola: se il controllo dei 4 angoli accende l'inseguimento ma
    # il moto MISURATO e LISCIATO (`Ms`, vedi `_liscia_angoli`) sposta gli angoli della zona dei tasti
    # di meno di mezzo tasto su tutto il pezzo, quel moto non si segue: vale la griglia del fotogramma
    # 0. Cosi' un pianoforte fermo non puo' far traballare la griglia nemmeno se la prima misura,
    # rumorosa com'e', ha detto "si muove".
    _zona_p = (0, 0, 848, 342)
    prova("moto nullo -> 0 tasti", prep0._moto_angoli([np.eye(3)] * 5, _zona_p, _Hp) == 0.0,
          f"{prep0._moto_angoli([np.eye(3)] * 5, _zona_p, _Hp)} tasti")
    _due = [np.eye(3) for _ in range(5)]
    _due[-1] = np.array([[1.0, 0.0, 2 * 33.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])   # +2 tasti in x
    prova("spostamento di 2 tasti agli angoli -> 2 tasti (sopra la soglia, il moto si tiene)",
          abs(prep0._moto_angoli(_due, _zona_p, _Hp) - 2.0) < 1e-6,
          f"{prep0._moto_angoli(_due, _zona_p, _Hp):.2f} tasti")
    _poco = [np.eye(3) for _ in range(5)]
    _poco[-1] = np.array([[1.0, 0.0, 0.4 * 33.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])   # 0,4 tasti in x
    _m = prep0._moto_angoli(_poco, _zona_p, _Hp)
    prova(f"0,4 tasti agli angoli -> sotto la soglia di {prep0._ANGOLI_MIN_TASTI}: il moto si butta",
          _m < prep0._ANGOLI_MIN_TASTI and _m > 0.3, f"{_m:.2f} tasti")
    prova("un moto illeggibile non si butta (inf)",
          not np.isfinite(prep0._moto_angoli([np.full((3, 3), np.nan)], _zona_p, _Hp)),
          "primo fotogramma non finito")
    # --- i fronti MISURATI: fin dove arrivano i tasti bianchi e neri (`lw_al_fronte`, `lb_al_fronte`) ---
    # Il modello disegna i tasti bianchi lunghi 6,2 e i neri 4,1 di quella lunghezza, e le due
    # costanti sono anche la SCALA della y (la punta dei neri è la riga da cui esce `passo_y`). Su
    # una tastiera lucida la faccia frontale del nero riflette la stanza, va sopra la soglia del
    # nero e il run scuro chiude prima: la punta esce corta di 15-20 px e, con lei, tutta la scala.
    # I due fronti misurati dicono ai DISEGNI dove finiscono davvero i tasti (il ritaglio, il
    # verdetto e la geometria del dataset non si toccano), e la coppia deve stare nei rapporti dei
    # pianoforti veri (il nero è il 56-64% del bianco).
    # Numeri veri dell'esempio 83 (`2024-09-04_20-09-07`, la ripresa dell'utente, 1920x1080):
    # fondo dei tasti a 442,2 px, punte dei neri MISURATE a 520,9 (passo_y 19,18 px per unità),
    # fronte dei bianchi a 603,6 e punta VERA dei neri a 539,4 (verificata pixel su pixel: a y 535
    # le barre scure dei neri ci sono ancora, a y 545 no).
    _rect_83 = (241, 437, 1416, 198)
    _vert_83 = {"fondo": (442.2, -0.00029), "punte": (520.9, 0.00979), "x_riferimento": 245.0,
                "passo_y": 19.18, "fronte": (603.6, 0.0), "fronte_neri": (539.4, 0.0)}
    _lw83 = prep0.lw_al_fronte(_vert_83, _rect_83, 1416)
    prova("esempio 83: il fronte dei bianchi si misura a ~8,4 unità (col tetto di prima, 1,35, si perdeva)",
          _lw83 is not None and abs(_lw83 - 8.42) < 0.03, f"{_lw83}")
    _lb83 = prep0.lb_al_fronte(_vert_83, _rect_83, 1416, _lw83)
    prova("esempio 83: la punta dei neri si misura a ~5,1 unità (il modello ne disegna 4,1)",
          _lb83 is not None and abs(_lb83 - 5.08) < 0.03, f"{_lb83}")
    prova("esempio 83: i due fronti arrivano nel rapporto dei pianoforti veri (0,60)",
          _lw83 and _lb83 and abs(_lb83 / _lw83 - 0.603) < 0.01, f"{_lb83 / _lw83:.3f}")
    prova("un fronte dei bianchi fuori misura (3,5 unità: il mobile o il tappeto) non si usa",
          prep0.lw_al_fronte(dict(_vert_83, fronte=(509.3, 0.0)), _rect_83, 1416) is None)
    prova("una punta dei neri più CORTA del modello (4,0) non si usa: la punta del modello è già dentro il tasto",
          prep0.lb_al_fronte(dict(_vert_83, fronte_neri=(518.7, 0.0)), _rect_83, 1416, _lw83) is None)
    prova("una punta dei neri lunga il doppio del modello (7,0) non si usa: non è un tasto",
          prep0.lb_al_fronte(dict(_vert_83, fronte_neri=(576.5, 0.0)), _rect_83, 1416, _lw83) is None)
    prova("neri sotto il 50% dei bianchi misurati (4,15 su 8,42) non si usano: non è un pianoforte",
          prep0.lb_al_fronte(dict(_vert_83, fronte_neri=(521.6, 0.0)), _rect_83, 1416, _lw83) is None)
    prova("senza le misure nessun fronte si inventa",
          prep0.lw_al_fronte({"fronte": None}, _rect_83, 1416) is None
          and prep0.lb_al_fronte({"fronte_neri": None}, _rect_83, 1416, _lw83) is None)
    prova("col fronte dei bianchi mancante i neri si tengono solo sotto il 72% del MODELLO",
          prep0.lb_al_fronte(dict(_vert_83, fronte_neri=(526.6, 0.0)), _rect_83, 1416) is not None
          and prep0.lb_al_fronte(_vert_83, _rect_83, 1416, None) is None)

    # E la misura della punta dei neri si prova su un fotogramma DISEGNATO, dove la punta la sa solo
    # il test: il modello con neri lunghi 5,0 e bianchi 8,4 unità (`_render_modello`, lo stesso
    # disegno che usa il passo 0). La misura deve ritrovare 5,0 unità, e `lb_al_fronte` le deve
    # passare ai disegni.
    _Ht = np.array([[8.0, 0.0, 60.0], [0.0, 8.0, 60.0], [0.0, 0.0, 1.0]])   # 8 px per unità
    _img_t = cv2.cvtColor(prep0._render_modello(_Ht, (200, 500), lw=8.4, lb=5.0)[0],
                          cv2.COLOR_GRAY2BGR)
    _x0t = float(prep0.G.proietta(_Ht, [(prep0.G.u_bianco(prep0.G.NOTA_MIN), 0.0)])[0][0])
    _x_neri_t = [_x0t + (prep0.G.u_nero(n) - prep0.G.u_bianco(prep0.G.NOTA_MIN)) * 8.0
                 for n in prep0.G.NERI]
    _fr_t = prep0.fronte_neri([(0.0, _img_t)] * 3, _x_neri_t, (60.0, 0.0),
                              (60.0 + prep0.G.LB * 8.0, 0.0), _x0t, 8.0, 8.0)
    # Mezzo pixel di margine: il tasto disegnato finisce sul pixel intero (la punta a v=5,0 cade a
    # y=100 e l'ultima riga scura è la 100 o la 101, secondo come `fillPoly` arrotonda il bordo).
    prova("su un fotogramma coi neri lunghi 5,0 unità la punta misurata è 5,0 (a mezzo pixel)",
          _fr_t is not None and abs(_fr_t[0] - (60.0 + 5.0 * 8.0)) < 1.5,
          "nessuna misura" if _fr_t is None else f"y {_fr_t[0]:.1f} contro {60.0 + 5.0 * 8.0:.1f} "
                                                 f"({_fr_t[2]} punti, {_fr_t[3]:.1f} px di dispersione)")
    _vert_t = {"fondo": (60.0, 0.0), "punte": (60.0 + prep0.G.LB * 8.0, 0.0), "x_riferimento": _x0t,
               "passo_y": 8.0, "fronte_neri": None if _fr_t is None else (_fr_t[0], _fr_t[1])}
    _lb_t = prep0.lb_al_fronte(_vert_t, (0, 0, 500, 200), 500, 8.4)
    prova("e `lb_al_fronte` la passa ai disegni: 5,0 unità (il modello ne disegna 4,1)",
          _lb_t is not None and abs(_lb_t - 5.0) < 0.2, f"{_lb_t}")

    # Il ritaglio stretto (`stringi_rettangolo`) tiene i margini CHIESTI: sopra il retro dei tasti
    # ci stanno le DITA, e chi raddrizza la striscia (progetto "video -> MIDI", `comune.V_LO`)
    # incomincia 2,4 unità SOPRA il retro (v = -2,4): senza quei margini la striscia esce nera
    # proprio in alto (misurato su `video5906842636420915152.mp4`: 9-10 righe nere su 144 prima,
    # 0 dopo). `--margine` deve arrivare lassù, e chiedendo meno del minimo storico (0,5 unità) il
    # ritaglio non deve stringersi ancora più di così.
    _rect_m = (0, 0, 500, 200)
    _s03 = prep0.stringi_rettangolo(_Ht, _rect_m, (200, 500), 0.3, 7.0)
    _s25 = prep0.stringi_rettangolo(_Ht, _rect_m, (200, 500), 2.5, 7.0)
    _s01 = prep0.stringi_rettangolo(_Ht, _rect_m, (200, 500), 0.1, 7.0)
    prova("il ritaglio stretto sale col margine chiesto (--margine 2.5: 2,0 unità in più di 0,3)",
          _s03 is not None and _s25 is not None and _s25[0][1] == _s03[0][1] - 16,
          "nessun ritaglio" if _s25 is None else f"y1 {_s25[0][1]} contro {_s03[0][1]}")
    prova("col margine chiesto la banda copre la finestra della striscia (2,4 unità sopra il retro)",
          _s25 is not None and _s25[0][1] <= 60.0 - 2.4 * 8.0 + 1,
          "nessun ritaglio" if _s25 is None else f"y1 {_s25[0][1]}")
    prova("chiedendo meno del minimo (0,5) il ritaglio non si stringe ancora",
          _s01 is not None and _s03 is not None and _s01[0] == _s03[0],
          "nessun ritaglio" if _s01 is None else str(_s01[0]))

else:
    print("  (0_prepara.py non trovato: salto i controlli sul verdetto)")

print(f"\n{sum(esiti)}/{len(esiti)} controlli passati")
sys.exit(0 if all(esiti) else 1)
