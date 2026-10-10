# 🎹 Piano Detector

Primo stadio della pipeline **video → MIDI**: dato un'immagine o un frame,
individua il riquadro (bounding box) del pianoforte e lo ritaglia.

## Come funziona

Usa **YOLOv8 pre-allenato su Open Images V7** (nessun training necessario),
sfruttando due classi:

- `Piano` → lo strumento intero (scelta prioritaria);
- `Musical keyboard` → i tasti (ripiego utile nei primi piani sulle mani).

Il riquadro scelto è quello con confidenza più alta tra i `Piano`; se non c'è,
si usa la migliore `Musical keyboard`.

## Modelli preaddestrati usati

Il progetto **non allena niente da zero**: mette insieme componenti già addestrate
da terzi e le fa cooperare.

| modello | pesi | cosa fa nel progetto |
|---|---|---|
| **YOLOv8l / YOLOv8m — Open Images V7** (Ultralytics) | `weights/yolov8l-oiv7.pt` (84 MB), `weights/yolov8m-oiv7.pt` (50 MB) | oggetto "Piano"/"Musical keyboard": trovare la tastiera (motore `pipeline`, `calibrato`, e passo "Prepara il video") |
| **MediaPipe HandLandmarker** (float16) | `weights/hand_landmarker.task` (7.4 MB) | 21 landmark per mano → dove stanno le dita (motore `pipeline`, filtro mani) |
| **PPAN — «Pay Attention to the Keys»** (ViT-S, ~84 MB) | nel progetto esterno `pianovision-ppan` | predice direttamente il piano roll dal ritaglio della tastiera (motore `ppan`) |

I quattro **motori** dello Studio li usano così:

- `pipeline` → YOLOv8 (riquadro tastiera) **+** MediaPipe (dita);
- `ppan` → la rete ViT-S pretrainata (nessun YOLO, nessun MediaPipe);
- `prospettica` e `calibrato` → **nessuna rete neurale**, solo `cv2`/`numpy`: la griglia dei
  88 tasti è ricostruita dalla sola geometria (YOLOv8 serve solo a stimare i 4 angoli
  della tastiera se non li segni a mano).

## Installazione

```bash
pip install -r requirements.txt
```

I pesi sono già in `weights/`:
- `yolov8l-oiv7.pt` — più preciso (**consigliato**);
- `yolov8m-oiv7.pt` — più leggero/veloce.

Se ti serve riscaricarli:
```bash
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8l-oiv7.pt -P weights/
```

## Uso — interfaccia web

```bash
python app.py
```
Apri http://127.0.0.1:7860, carica un'immagine, regola soglia e margine.

## Uso — Studio web (video → MIDI, con player)

```bash
python3 pipeline_web.py
```
Apri http://127.0.0.1:7862: carica un video qualsiasi (mp4, mov, mkv, webm…), scegli il
**motore**, regola i parametri e premi **Esegui**. A fine esecuzione la pagina mostra:

- statistiche e tabella degli eventi nota;
- `prima_griglia.jpg` (griglia disegnata sui tasti reali) e `debug.mp4` (mani + note attive);
- il **piano roll** con tastiera virtuale e il **player**, che legge davvero `song.mid`
  (parser Standard MIDI File + sintesi Web Audio: nessuna libreria esterna, nessun CDN,
  nessun file audio scaricato).

Ogni esecuzione lavora in `web_runs/<id>/` (video caricato + `out/`). La pagina elenca le
esecuzioni precedenti: si possono riaprire o eliminare con **Pulisci**.

Note operative:

- il ramo “mani” richiede `mediapipe`: il server usa automaticamente il primo venv del
  progetto (`.venv-mp10`), altrimenti l'interprete corrente. Con la casella “senza mani”
  la pipeline gira anche senza mediapipe e serve a controllare solo la griglia;
- la casella “normalizza con ffmpeg” converte prima il video in H.264/yuv420p: serve per i
  `.mov` HEVC del telefono, per la rotazione nei metadati e per le risoluzioni dispari;
- il server rifiuta l'avvio se resta meno di 1 GB libero su disco (i video occupano spazio).

### Due motori (stesso formato di uscita)

Il selettore **Motore** in cima ai parametri decide *chi* trascrive il video:

| motore | come funziona | quando conviene |
|---|---|---|
| **pipeline** (default) | YOLOv8 trova la tastiera, `keyboard_grid.py` stima i tasti, mediapipe segue le dita, le pressioni nascono dalla profondità del polpastrello | inquadrature frontali/dall'alto, tastiera ben visibile; è l'unico che assegna anche la **mano** |
| **PPAN — “Pay Attention to the Keys”** | la tastiera viene ritagliata e raddrizzata in una striscia di 88 tasti e una **rete pretrainata** (ViT-S, 84 MB) predice direttamente il piano roll | video reali con inquadratura obliqua, mani fuori campo, luce difficile: **molto più robusto** della geometria euristica |

Il motore PPAN vive nel progetto `PianoviVision-PPAN`
(`~/.cline/data/workspaces/chat/pianovision-ppan`, lo stesso di `PianoviVision-PPAN` sul
Desktop): il server lo lancia come sottoprocesso con **il suo venv** (torch + transformers) e
poi `ppan_bridge.py` converte l'uscita di PPAN nello schema della pipeline
(`out/notes.json`) e disegna `out/prima_griglia.jpg` con **la regione usata da PPAN** e la
striscia 720×122 raddrizzata che la rete ha analizzato. Così tabella, statistiche, player
MIDI e download funzionano identici con entrambi i motori.

Dettagli utili su PPAN:

- **il ritaglio è la cosa che conta di più**: senza indicazioni PPAN stima da solo la
  tastiera (spesso bene), ma con **🎯 Segna i 4 angoli sul video** si clicca la tastiera sul
  preview e i 4 punti vengono passati al modello (`--quad`, ordine sistemato in automatico;
  i punti si trascinano per correggerli, **↺ auto** torna alla stima automatica). Misurato
  su un video reale: con il ritaglio automatico 1 nota, con i 4 angoli segnati a mano 2 note
  e altezze corrette;
- la cartella è modificabile dal campo *Cartella PPAN* (o con la variabile `PPAN_DIR`): deve
  contenere `ppan_infer.py`, `weights/pytorch_model.bin` e `weights/config.json`;
- gira su **MPS** (o CPU), elabora a **30 fps fissi** e costa circa **1 s per secondo di
  video** (più ~5 s per caricare i pesi la prima volta);
- **0 note è quasi sempre un ritaglio sbagliato**, non un modello scarso: se la stima
  automatica inquadra qualcosa che non è la tastiera (su un video di prova ha preso **lo
  spartito** sul leggio, 0 note in 6.4 s) il job finisce comunque "fatto" ma vuoto, e lo Studio
  lo dice in chiaro: avviso nel log e nel riquadro dell'esito che rimanda a `prima_griglia.jpg`
  (la striscia in basso è ciò che vede la rete) e ai 4 angoli segnati a mano;
- **serve la tastiera intera in campo**: la striscia è sempre 88 tasti (A0–C8) e PPAN non ha
  alcuna opzione per una tastiera parziale, quindi se il video inquadra solo una parte dei tasti
  le note vengono trovate ma le **altezze sono sbagliate**. Misurato su un video che mostra ~15
  tasti bianchi: 0 note con il ritaglio automatico (prendeva lo spartito) e 25 note con i 4 angoli,
  ma distribuite su 62 semitoni (36→98) invece dei ~25 tasti reali;
- non conosce la **mano** (la colonna resta vuota) e assume sempre la tastiera completa
  **A0–C8** (21–108), quindi non ha bisogno di `--prima-nota`;
- se il motore non è disponibile la pagina lo disabilita e spiega cosa manca; la pipeline
  resta sempre utilizzabile.

Nel riquadro dell'esito, quando un'esecuzione **pipeline** finisce con poche note, compare il
pulsante *Riprova questo video con PPAN*: rilanciare lo stesso file senza ricaricarlo.

## Uso — riga di comando

```bash
python piano_detector.py foto.jpg -o output/
python piano_detector.py frame1.jpg frame2.jpg --conf 0.10 --margine 0.05 --all
```

Per ogni immagine produce:
- `*_annotata.jpg` — immagine con il riquadro (verde = scelto, azzurro = alternative);
- `*_crop.jpg` — il ritaglio del pianoforte;
- coordinate JSON su stdout.

Opzioni: `--conf` (soglia), `--margine` (padding 0-1 attorno al box),
`--all` (salva il crop di ogni rilevazione), `-w` (pesi diversi).

## Uso come libreria (per la pipeline video)

```python
from piano_detector import PianoDetector

det = PianoDetector("weights/yolov8l-oiv7.pt", conf=0.15)

# su file
box = det.detect_piano("frame.jpg")          # PianoBox(x1,y1,x2,y2,confidenza,classe)
crop = det.crop_piano("frame.jpg", "out.jpg", margine=0.05)

# su frame OpenCV (np.ndarray BGR) — pronto per il loop video
import cv2
cap = cv2.VideoCapture("video.mp4")
ok, frame = cap.read()
if ok:
    box = det.detect_piano(frame)
```

## Note e limiti note

- Funziona molto bene su: primi piani dei tasti, inquadrature dall'alto,
  pianoforti (a coda o verticali) ben visibili nella scena.
- Può mancare pianoforti **molto piccoli/lontani** in ambienti ampi e affollati;
  in quel caso abbassa `--conf` (es. 0.05). Per i tuoi video (persona che suona)
  il piano è in genere grande nel frame, quindi non è un problema.
- Per il tracking frame-by-frame, un'ottimizzazione futura è rilevare il piano
  solo nel 1° frame e poi tracciarlo (es. IoU tra box consecutivi / tracker),
  ricalcolando solo quando la confidenza scende.

## Motore «calibrato» (sagome per nota)

Terzo motore dello Studio. Per il video caricato il software **misura da solo dove sta ogni tasto in
ogni frame** (un rettangolo per nota = la *sagoma*), scrive **una clip per nota inquadrata** (tutta la
durata del video, solo il crop di quella nota) e decide premuto/rilasciato dentro il riquadro.

```bash
python3 motore_calibrato.py video.mp4 -o out/ --quad "x,y x,y x,y x,y" --cartella-sagome run/
python3 test_sagome.py        # suite sintetica con verita' a terra
```

- `sagome.py`: `regione_tastiera`, `riquadri_per_frame`, `scrivi_clip_per_nota`, `salva_sagome`, `carica_sagome`.
- `motore_calibrato.py`: `RilevatoreCalibrato.analizza()` -> `notes.json`, `song.mid`, `prima_griglia.jpg`,
  `sagome.json`, `sagome/NNN.mp4` (le clip stanno in `web_runs/<id>/sagome/`, come in §F del brief).
- Rotte: `POST /api/job` con `motore=calibrato`, `GET /api/job/<id>/sagome.json`, `GET /api/job/<id>/clip/<nota>`.
  Caricando un nuovo video con questo motore si **cancellano** `sagome.json` e `sagome/` delle esecuzioni precedenti.
- Regole: nota non inquadrata -> mai emessa (`emesse ⊂ visibili`, verificato con un'asserzione);
  tasto tenuto = una nota; ottava ambigua -> `scelta: null` + lista `candidate` + `ipotesi_usata`, mai in silenzio.

**Numeri misurati (video SINTETICO 1600x600, 8 s, 240 frame, tastiera parziale C3..C6, 37 note inquadrate su 88):**

| prova | risultato |
|---|---|
| tasti inquadrati | 37/88 (48..84), larghezza bianco misurata 59.99 px (vera 60) |
| senza mano finta, 8 note premute | 8 emesse, 8 eventi, 0 spurie (test A) |
| con una mano finta che passa sopra i neri | 7/8 note vere trovate, **23 eventi spuri sui neri** |
| tastiera intera 52 bianchi | 88 note inquadrate, ottava univoca (prima nota 21) |
| una sola ottava (8 bianchi) | ambigua: 7 candidate dichiarate |
| clip | 240 frame ciascuna = n_frame; 90x328 px (bianchi); 36 clip = 724 KB contro 1223 KB del video |

**Limiti noti:** misurato solo su video sintetici (mai su un video reale, mai con YOLO: nel mio ambiente non ci sono
i pesi); un dito che sfiora un tasto senza premere cambia l'immagine come uno che preme, quindi le mani sopra i neri
producono falsi positivi; le soglie (`--soglia-giu/su`, scala 25 livelli di grigio) vanno tarate sul video reale;
`riquadri` tiene un oggetto per nota e per frame (video molto lunghi = molta RAM).
