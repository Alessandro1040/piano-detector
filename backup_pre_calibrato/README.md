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
