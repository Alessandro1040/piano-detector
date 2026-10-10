# HANDOFF — pipeline video → MIDI (per una nuova chat di Cline)

> Incolla questo messaggio in una chat nuova, quando avrai i file di Claude.
> È scritto per essere autosufficiente: la chat nuova non ricorderà nulla.

---

## Il progetto

Progetto di **computer vision**: da un video di una persona che suona il
pianoforte, produrre un file **MIDI**. Scelta deliberata: **usare solo il video,
niente audio.** L'obiettivo è che l'informazione venga dalle immagini — non
proporre la trascrizione audio, è una decisione già presa e motivata. Sappiamo
che l'audio sarebbe più accurato e l'abbiamo scartato di proposito.

Cartella: `/Users/alessandrolocurcio/Downloads/piano-detector/`

| file | stato |
|---|---|
| `piano_detector.py` | stadio 1 — **fatto, verificato, CONGELATO: non modificarlo** |
| `app.py` | UI Gradio su singola immagine — congelato |
| `video_app.py` | viewer Flask frame-by-frame — fatto, verificato in Chrome reale |
| `video_viewer.html` | UI del viewer — fatto |
| `BRIEF_CLAUDE.md` | **specifica dello stadio 2: leggilo per intero prima di toccare nulla** |
| `README.md`, `requirements.txt` | contesto |
| `weights/yolov8{m,l,x}-oiv7.pt` | pesi già scaricati |
| `demo_video.mp4` | video di test |
| `test_images/`, `demo_output/` | materiale di prova |

## Prima di scrivere qualsiasi riga

1. Leggi **`/Users/alessandrolocurcio/Downloads/piano-detector/BRIEF_CLAUDE.md`**
   (482 righe): contiene i 6 moduli richiesti con firme esatte, lo schema
   `notes.json`, i divieti, la definition of done e le 5 decisioni chiave.
2. Leggi **`piano_detector.py`**: è l'API reale dello stadio 1, da importare.
3. Controlla tu stesso le versioni installate (§ sotto): non fidarti della
   documentazione generica, su questa macchina è diversa.

## Stato dello stadio 1 (fatto)

`PianoDetector` — YOLOv8 pre-allenato su Open Images V7, classi `piano` e
`musical keyboard`. API: `detect_all(img)`, `detect_piano(img, margine)`,
`crop_piano(...)`, `annota(...)`, dataclass `PianoBox`. Accetta `np.ndarray` BGR
o path. `detect_piano` preferisce `piano` e ripiega su `musical keyboard`.
Verificato end-to-end (round-trip `/detect`, browser reale via CDP, 0 eccezioni JS).

## Fatti verificati sull'ambiente — non indovinarli

macOS, **Apple M5**, 16 GB, **Python 3.14.6 arm64**.

Installati: `cv2` **5.0.0**, `torch` 2.14.0 (**MPS attivo**, no CUDA),
`torchvision` 0.29.0, `ultralytics` 8.4.171, `numpy` 2.4.6, `Pillow` 12.3.0,
`onnxruntime` 1.30.0 (CoreML), **`pretty_midi` 0.2.11**, `mido`, `scipy`,
`librosa`, `soundfile`, `torchaudio`, `flask`, `gradio`, `ffmpeg`+`ffprobe`
in `/opt/homebrew/bin/`. Assenti: `mediapipe`, `transformers`, `basic_pitch`.

### ⚠️ Tre trappole che rompono il codice alla prima esecuzione

1. **OpenCV 5.0.0: `cv2.legacy` è stato rimosso.**
   `TrackerCSRT_create`, `TrackerKCF_create`, `TrackerMOSSE_create` → **non
   esistono**. Presenti solo `TrackerMIL/Vit/Nano/DaSiamRPN`. Qualsiasi snippet
   che usa CSRT/MedianFlow va riscritto (template matching è la scelta preferita).
2. **MediaPipe 1.0.1 non ha `mp.solutions`** (verificato: zero file `solutions`
   nel wheel). Serve l'API Tasks: `mediapipe.tasks.python.vision.HandLandmarker`
   con `RunningMode.VIDEO`. Modello:
   `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`
   (7 819 105 byte, verificato HTTP 200) → `weights/hand_landmarker.task`.
3. **Installare mediapipe tocca OpenCV**: trascina
   `opencv-contrib-python-5.0.0.93` che co-installa con `opencv-python`
   (entrambi forniscono `cv2`). **Dopo l'installazione, riverifica i tracker.**

### Fatti misurati su `demo_video.mp4`

- 1280×720, 30 fps, 360 frame, 12 s, **nessuna traccia audio** (unico stream h264).
- Rilevazione tipica (yolov8m, conf 0.15):
  `musical keyboard` 0.386 → box (151, 15, 1132, 391)
  `piano` 0.237 → box (153, 4, 1131, 636)
- **Il box `piano` copre lo strumento intero** (fino a y2=636: corpo, gambe),
  **NON i tasti.** Per la griglia della tastiera va usato `musical keyboard`.
  Non ereditare da `detect_piano()` la preferenza per `piano`: è giusta per
  "dov'è il pianoforte", sbagliata per "dove sono i tasti".
- Le confidenze sono **basse** (0.24–0.49) e il margine spesso ~0%: nessuna
  soglia a 0.5, nessuna geometria che presupponga un box preciso.

---

## Cosa devi fare adesso

Claude ha scritto i 6 moduli di §E del brief:
`keyboard_tracker.py`, `hands.py`, `keyboard_grid.py`, `note_events.py`,
`to_midi.py`, `pipeline.py`. **Te li incollerò nella chat** (o li troverai già
nella cartella).

Il tuo compito: **integrarli, verificarli ed ESEGUIRLI davvero.** Non fidarti del
codice perché "sembra giusto": è stato scritto senza poter eseguire nulla su
questa macchina. Le tre trappole sopra sono esattamente i motivi per cui un
codice plausibile può crashare alla prima riga.

### Protocollo di verifica (in quest'ordine)

**1. Salva i file** nella cartella del progetto. Non riscrivere `piano_detector.py`.

**2. Compilazione**
```bash
cd /Users/alessandrolocurcio/Downloads/piano-detector
python3 -m py_compile keyboard_tracker.py hands.py keyboard_grid.py note_events.py to_midi.py pipeline.py
```

**3. Ricerca statica dei divieti** (se esce qualcosa, va corretto):
```bash
cd /Users/alessandrolocurcio/Downloads/piano-detector
grep -n 'TrackerCSRT\|TrackerKCF\|TrackerMOSSE\|cv2\.legacy\|solutions\.hands\|mp\.solutions\|import transformers\|grounding\|torch\.hub\|# TODO\|pass  #' keyboard_tracker.py hands.py keyboard_grid.py note_events.py to_midi.py pipeline.py
```

**4. Esecuzione senza mani** (must-pass, non richiede mediapipe):
```bash
cd /Users/alessandrolocurcio/Downloads/piano-detector
python3 pipeline.py demo_video.mp4 -o out_test/ --limite 60 --senza-mani
```
Deve terminare **senza eccezioni** e produrre `out_test/prima_griglia.jpg`.

**5. Validazione visiva della griglia** — il test più importante:
apri `out_test/prima_griglia.jpg` e **guardala**. I tasti disegnati devono
cadere **sui tasti veri**, non sul corpo del pianoforte. Se la griglia è
spostata di un'ottava, il MIDI sarà corretto ma **trasposto**: è l'errore più
subdolo del progetto. Riporta cosa vedi, non quello che speri.

**6. Mani** — installa mediapipe e scarica il modello (attenzione trappola 3):
```bash
python3 -m pip install mediapipe
mkdir -p weights && curl -L -o weights/hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
# poi RIVERIFICA i tracker, perché opencv-contrib-python può aver sostituito cv2:
python3 -c "import cv2; print(cv2.__version__, hasattr(cv2,'TrackerMIL_create'))"
```
poi ripeti il passo 4 **senza** `--senza-mani` e con `--debug-video`.

**7. Il MIDI**
```bash
python3 -c "
import pretty_midi, json
pm = pretty_midi.PrettyMIDI('out_test2/song.mid')
n = [x for i in pm.instruments for x in i.notes]
print('note:', len(n))
print('gamma:', min(x.pitch for x in n), max(x.pitch for x in n) if n else '-')
print('malformate (end<=start):', sum(1 for x in n if x.end <= x.start))
print('duplicati aperti:', sum(1 for x in n if x.pitch < 0 or x.pitch > 127))
"
```

**8. Riporta con evidenza.** Numeri, comandi, output reali. Se qualcosa non
funziona, l'errore esatto e l'ipotesi — non un riassunto vago. E dimmi
**cosa manca** rispetto a §E/§G del brief, non solo cosa gira.

## Aspettative oneste (da condividere, non da nascondere)

L'obiettivo realistico **non** è una trascrizione fedele. Gli errori non saranno
bug da correggere ma il **tetto della sorgente**: polpastrello largo 3-4 pixel a
720p, motion blur, prospettiva, e occlusione (una mano copre l'altra). Il
traguardo è una **prima versione che gira end-to-end e produce un `.mid` non
vuoto**, con la geometria della griglia verificabile a occhio. Poi si stringe
misurando.

## Come si valida l'accuratezza (problema aperto)

`demo_video.mp4` è **muto**: non esiste verità di riferimento, quindi non si può
dire "12 note su 15 corrette". Due strade:
1. un video di cui si conoscono le note (scala, accordi, pezzo noto);
2. **video sintetico generato** con OpenCV/PIL: un disegno di tastiera con
   "dita" che premono tasti noti → verità di riferimento perfetta, e isola la
   **geometria della griglia** dall'incertezza di YOLO+MediaPipe. Se il MIDI è
   corretto lì, ogni errore sui video veri viene dal riconoscimento, non dalla
   griglia. Questa è la strada da preferire per misurare davvero l'errore.

## Come lavorare

- Fai i passi, non chiedere permesso a ogni comando: esegui e mostra i risultati.
- Verifica **eseguendo**, non leggendo. Se un modulo non è eseguibile, dillo.
- Non riscrivere lo stadio 1 e non "migliorare" `piano_detector.py`: è l'unica
  parte verificata in browser reale.
- Se il codice di Claude ha un difetto, **correggilo tu** e spiega cosa hai
  cambiato e perché, invece di rimandare il problema.

---

# ESITO DELL'INTEGRAZIONE (verificato)

## 1. I 6 moduli di Claude sono integrati

`pipeline.py`, `keyboard_tracker.py`, `hands.py`, `keyboard_grid.py`,
`note_events.py`, `to_midi.py` sono nella cartella e sono **byte-identici** a
quelli consegnati (`files.zip` / `files/`): nessuna modifica necessaria.
`python3 -m py_compile` passa su tutti i file.

## 2. Definition of done (§G) — esito

| # | requisito | esito |
|---|---|---|
| 1 | `py_compile` su tutti i file | ✅ |
| 2 | `--senza-mani` senza eccezioni + `prima_griglia.jpg` | ✅ (60/60 frame, `out_test/`) |
| 3 | con mani: `notes.json` non vuoto, on/off bilanciati | ✅ (2 eventi, pitch 59–61) |
| 4 | `.mid` apribile con `pretty_midi`, gamma 21–108 | ✅ (59–61, 0 malformate) |
| 5 | nessun import vietato | ✅ (`cv2.legacy`, CSRT/KCF/MOSSE, `mp.solutions`, `transformers`, `torch.hub` assenti) |
| 6 | nessun download a runtime | ✅ |
| 7 | nomi di dominio in italiano | ✅ |

Comando verificato (video intero, 360 frame, 12 s):

```bash
.venv-mp10/bin/python pipeline.py demo_video.mp4 -o out_test2/ --debug-video
# -> EXIT 0; out_test2/{notes.json, song.mid, prima_griglia.jpg, debug.mp4}
```

Ispezione visiva di `prima_griglia.jpg`: le verticali verdi separano i tasti
bianchi reali, i tasti neri sono allineati e le etichette C3…G5 sono leggibili
→ la griglia **cade sui tasti veri** (l'ottava assoluta resta un'ipotesi finché
non si passa `--prima-nota`, come previsto dal brief).

## 3. ⚠️ mediapipe: NON usare 1.0.1 — bug upstream

`mediapipe==1.0.1` (l'unico wheel per Python 3.14 su PyPI) è **rotto**: ogni
grafo Tasks Vision con `TensorsToDetectionsCalculator` (HandLandmarker incluso)
fa `SIGABRT` all'apertura del grafo:

```
F graph_service.h:139] Check failed: service_ Service is unavailable.
@ -[DrishtiMetalHelper initWithCalculatorContext:]
@ mediapipe::api2::TensorsToDetectionsCalculator::Open()
```

`BaseOptions(delegate=BaseOptions.Delegate.CPU)` **non** aiuta. È un bug noto e
ancora aperto a monte: `google-ai-edge/mediapipe#6356`
(«1.0.1 è l'unica versione per Python 3.14 → nessun fallback in-versione»).

**Soluzione adottata:** `mediapipe==0.10.35`, che è un wheel
`py3-none-macosx_11_0_arm64.whl` → si installa su Python 3.14 e **funziona in
CPU** (verificato: mani rilevate con confidenza 0.94–0.99). Nessun Python 3.11
necessario. Installato in un venv isolato così da **non toccare** il `cv2` 5.0.0
di sistema (trappola 3 del brief):

```bash
cd /Users/alessandrolocurcio/Downloads/piano-detector
python3 -m venv --system-site-packages .venv-mp10
.venv-mp10/bin/python -m pip install --no-deps mediapipe==0.10.35
```

`hands.py` **non è stato modificato**: il difetto non era nel suo codice ma nel
wheel 1.0.1.

## 4. Come si esegue

- **Solo griglia/tastiera (nessuna dipendenza extra):**
  `python3 pipeline.py demo_video.mp4 -o out_test/ --limite 60 --senza-mani`
- **Pipeline completa con le mani:** usare il venv
  `.venv-mp10/bin/python pipeline.py demo_video.mp4 -o out_test2/ --debug-video`
  (il `python3` di sistema non ha mediapipe).

## 5. Limiti onesti

La demo `demo_video.mp4` è **muta e non è un'esecuzione musicale reale**: il
risultato (2 eventi, 8.0–11.0 s) è coerente con quel materiale, non una misura
di accuratezza. Per misurare davvero l'errore serve la verità di riferimento
(§«Come si valida l'accuratezza»): video sintetico con tasti noti oppure un
video di una scala/accordo.
