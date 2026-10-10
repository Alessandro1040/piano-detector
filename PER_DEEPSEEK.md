# piano-detector — contesto per DeepSeek (UN solo file)

> **Come usarlo:** allega **solo questo file** a DeepSeek e incolla come messaggio il blocco di §1.
> Contiene tutto il necessario: descrizione, architettura, vincoli, il problema aperto e il
> codice dei moduli rilevanti (in fondo, §7).

---

## 1. MESSAGGIO DA INCOLLARE A DEEPSEEK

> Ti allego un unico file con tutto il contesto di **`piano-detector`**, un mio progetto che da un
> **video di una persona che suona il pianoforte** produce un **file MIDI**, usando **solo il
> video** (l'audio è escluso di proposito: decisione già presa). Voglio un **consiglio su come
> procedere**.
>
> **Obiettivo.** Dal video alla trascrizione MIDI (note, onset/offset, velocity), **senza audio**,
> **senza training di reti nuove**: usare solo modelli pretrainati presenti in locale.
>
> **Stato.** Ho quattro motori (stesso formato di uscita `out/notes.json` + `out/song.mid`), vedi
> §3. Il motore più recente è **`prospettica`** (`motore_prospettica.py` + `griglia_prospettica.py`),
> che stima la griglia dei tasti **dalla sola geometria** dell'immagine (profilo verticale dei tasti
> neri + NCC), **senza YOLO né mediapipe**, per reggere le inquadrature oblique a mano libera.
>
> **Problema di fondo.** La qualità della trascrizione dipende dalla **geometria della tastiera**:
> piccoli errori sulla griglia dei tasti → note trasposte. Il motore `calibrato` più vecchio ha una
> misura dei tasti sbagliata dentro `sagome.py` (su un video di prova trova ~7 note invece di ~45);
> `prospettica` è il tentativo di risolvere lo stesso problema. Nel codice (§7) ci sono i moduli
> chiave: `piano_detector`, `keyboard_grid`, `keyboard_tracker`, `motore_calibrato`, `sagome`,
> `motore_prospettica`, `griglia_prospettica` (il server `pipeline_web.py` e i frontend sono
> omessi, li fornisco se servono).
>
> **Aggiornamento.** Ho già applicato i tre fix sulla soglia del cambio di inquadratura in
> `motore_prospettica.py`: soglia 20 → 38, conferma del nuovo anchor su 3 frame concordi, controllo
> di evidenza sul salto. Effetti misurati in **§5.1** (8 falsi "cambi di inquadratura" → 0, 75 → 52
> eventi, 8 → 0 eventi su tasti non inquadrati), con i tagli veri ancora gestiti. Il codice in §7 è
> già quello aggiornato.
>
> **Domanda.** Rispetto a questo obiettivo e a questi motori, **come procederesti?** In particolare:
> (a) conviene consolidare/estendere `prospettica` o ripiegare su `ppan` (§3); (b) come rendere la
> stima della griglia **robusta** (validazioni, gestione dei fallimenti, note fuori inquadratura,
> ambiguità dell'ottava); (c) esiste un'architettura migliore che riusa ciò che ho già, **senza
> aggiungere dipendenze e senza training**? Dammi una raccomandazione chiara e i passi operativi in
> ordine di priorità. Se qualcosa non è deducibile dal materiale, dimmi cosa ti manca.

---

## 2. Il progetto in breve

- **Cartella:** `/Users/alessandrolocurcio/Downloads/piano-detector/`
- **Scopo:** video → MIDI, **solo video** (niente audio). Modelli pretrainati, niente training.
- **Studio web:** `python3 pipeline_web.py` → **http://127.0.0.1:7862** (Flask). Ogni esecuzione vive
  in `web_runs/<id>/` con `out/` (`notes.json`, `song.mid`, `prima_griglia.jpg`, `griglia.mp4`).
- **Stadio 1 (congelato):** `piano_detector.py` — YOLOv8 pretrainato su Open Images V7, classi
  `piano` e `musical keyboard`, nessun training.
- **Stadio 2 (verificato):** `pipeline.py`, `keyboard_tracker.py`, `hands.py`, `keyboard_grid.py`,
  `note_events.py`, `to_midi.py`.

---

## 3. I quattro motori

| motore | file | come funziona | note |
|---|---|---|---|
| `pipeline` | `pipeline.py` | YOLOv8 trova la tastiera → `keyboard_grid` stima la geometria → mediapipe segue le dita → pressioni dalla profondità del polpastrello | unico che assegna la **mano**; debole sulle inquadrature oblique (griglia che "scivola" di un tasto) |
| `ppan` | progetto esterno *PianoviVision-PPAN* (`ppan_infer.py`, ViT-S pretrainata) | la rete legge il video e predice il piano roll | robusto sul reale; assume sempre la tastiera intera A0–C8, non conosce la mano |
| `calibrato` | `motore_calibrato.py` + `sagome.py` | misura **dove sta ogni tasto in ogni frame** (un riquadro per nota = "sagoma"), ne ricava una clip per nota e decide premuto/rilasciato nel riquadro | punto debole: la **misura geometrica** della griglia |
| `prospettica` (default recente) | `motore_prospettica.py` + `griglia_prospettica.py` | ricostruisce la griglia dei tasti dalla sola geometria (profilo verticale + NCC), la riaggancia a ogni cambio di inquadratura | senza YOLO né mediapipe; è il motore su cui sto lavorando |

**Uscita comune** (schema semplificato di `out/notes.json`), così lo Studio non ha casi speciali:

```json
{ "fps": 30.0, "frame_totali": 303, "durata_s": 10.1,
  "estensione_tastiera": { "prima_nota": 48, "ultima_nota": 78, "n_tasti": 31 },
  "eventi": [ { "nota": 72, "nome": "C5", "onset": 0.0, "offset": 2.567,
                "durata": 2.567, "velocity": 127, "profondita": 1.0, "mano": "" } ] }
```

---

## 4. Vincoli (importante: rispettarli)

**Congelati / non riscrivere:** `piano_detector.py`, `app.py`, `video_app.py`, `video_viewer.html`
e i moduli dello stadio 2 (`pipeline.py`, `keyboard_tracker.py`, `hands.py`, `keyboard_grid.py`,
`note_events.py`, `to_midi.py`). **PPAN è di sola lettura.** `keyboard_grid.py` e
`keyboard_tracker.py` si importano (estensioni sì, riscritture no).

**Niente nuove librerie** oltre `cv2`/`numpy`/`Pillow`/stdlib (+ `ffmpeg`/`ffprobe` come processo).
Divieti espliciti: `cv2.legacy`, `TrackerCSRT/KCF/MOSSE`, `mp.solutions`, `mediapipe==1.0.1`,
`transformers`, `torch.hub`. **Nessun download a runtime.** Il server Flask **non** importa
torch/mediapipe: il lavoro pesante gira in un sottoprocesso.

**Ambiente verificato:** macOS, **Apple M5**, 16 GB, **Python 3.14.6 arm64**; `cv2` **5.0.0**
(⚠️ `cv2.legacy` **rimosso**), `torch` 2.14.0 (**MPS**, no CUDA), `ultralytics` 8.4.171,
`numpy` 2.4.6 (NumPy 2.x), `Pillow` 12.3.0, `pretty_midi` 0.2.11, `flask` 3.1.3,
`ffmpeg`/`ffprobe` in `/opt/homebrew/bin/`, `mediapipe` **0.10.35** (⚠️ **non** 1.0.1: bug
upstream SIGABRT) installato nel venv `.venv-mp10` per il solo ramo "mani".

---

## 5. Il problema attuale (in breve)

La trascrizione è trascinata dalla **geometria della tastiera**. Due tentativi:

1. **`calibrato`** (`sagome.py`): la misura dei tasti è sbagliata — la banda dei tasti neri e la
   "fascia frontale" sono stimate male, quindi la griglia **non cade sui tasti** (su `test_shotC.mp4`
   trova **~7 note** invece di ~45–50; su altri video va in `RuntimeError`). Le evidenze sono
   descritte in dettaglio nel file `per_claude/00_LEGGIMI_PER_CLAUDE.md` del progetto (non allegato).
2. **`prospettica`** (`griglia_prospettica.py`): stima la griglia dalla sola geometria e la riaggancia
   ai cambi di inquadratura. Su un'ultima esecuzione reale (video verticale 720×1280, 303 frame,
   10.1 s) ha prodotto: **31 tasti inquadrati (48..78)**, 75 eventi su 26 note uniche, 7–8 cambi di
   inquadratura rifatti da zero (§5.1).

### 5.1 Aggiornamento: i fix sono già applicati (misurati)

I tre interventi sulla soglia del cambio di inquadratura sono **già dentro** `motore_prospettica.py`
(il codice in §7 è quello aggiornato) e sono il comportamento **di default**: nessun flag nuovo.

Misura sullo stesso video verticale del caso 2, stesso codice per entrambi i lati, unica differenza
il fix:

| | prima | dopo |
|---|---|---|
| "cambi di inquadratura" (tutti falsi) | 8 (frame 282–301) | **0** |
| salto massimo della griglia | 0.542 larghezze di tastiera | **0.031** |
| tasti inquadrati | 33 (47..79, di cui 9 inventati) | 22 (53..74) |
| eventi / note uniche | 75 / 26 | 52 / 21 |
| eventi su tasti fuori inquadratura (48–52) | 8 | **0** |

Su un taglio **vero** (video di prova costruito unendo `test_shotA` + `test_shotC`, stacco al frame
122) il taglio viene ancora adottato, con 2 frame di ritardo: `cambio di inquadratura confermato (64
livelli, 3 frame concordi)`; la griglia per frame resta quella di prima (scarto massimo 0.051
larghezze di tastiera, note finali identiche).

Le tre parti, in `motore_prospettica.py`:
- **Fix A** — `_SOGLIA_TAGLIO = 38.0` (era `20.0`): uno stacco vero sta a 60+, un movimento brusco a
  20–30. Superarla ora significa **sospetto**, non più "griglia rifatta subito".
- **Fix B** — la griglia candidata si adotta solo dopo `_CONFERME_TAGLIO = 3` frame in cui
  `_distanza_griglie` (accordo < 0.15 larghezze) dice che è **la stessa scena**: una mano che passa
  o una luce che cambia dà un anchor diverso a ogni frame, quindi non regge.
- **Fix C** — un salto > 0.30 larghezze è credibile solo se la scena nuova "spiega" i tasti almeno
  quanto quella in uso (`_evidenza` ≥ 0.80 in assoluto **oppure** non peggiore di 0.05 rispetto alla
  griglia attuale: nei video scuri la tastiera vera sta a 0.62–0.79, quindi il solo 0.80 assoluto
  bloccherebbe anche i tagli veri). Se il candidato insiste per `_TAGLIO_OSTINATO = 15` frame lo si
  adotta comunque.

**Resta aperto** (ed è la parte su cui serve il consiglio): con il fix il video verticale resta su
**22 note inquadrate (53..74)** e 52 eventi. Se la tastiera suonata è più estesa, il limite a monte è
che `_ancora` aggancia **solo la porzione inquadrata** e l'estensione non viene dedotta dall'immagine
(esiste `--prima-nota` per l'ottava, ma non un'estensione misurata).

### 5.2 Caso nuovo: tastiera **lontana** nell'inquadratura (i neri sono sotto la soglia di larghezza)

Video `video5906842636420915152.mp4`, **848×464**, 224 frame: pianoforte intero inquadrato ma piccolo
(i neri sono larghi **6–7 px**, il passo bianco reale ~10.5 px, i 36 neri dell'88 tasti tutti visibili).

Prima: **15 eventi / 10 note uniche**, `inlier 0` su tutta la serie, evidenza 0.82–0.89 (alta e
ingannevole), "19 tasti inquadrati (48..66)".

Causa (misurata): in `_H_iniziale_classico` il minimo di larghezza dei neri era `lo = 0.015*w` =
**12.7 px** a w=848, quindi **nessun nero vero passava il filtro** (i run accettati erano solo blob di
sfondo larghi 23–59 px). L'ancoraggio classico (spaziature dei neri) non poteva funzionare e restava
solo `H_profilo`, che aggancia a **76.4 px** = 7.5× il passo vero: da lì `affina` = 0 inlier.

Fix, due punti in `griglia_prospettica.py`, nessun flag nuovo, nessuna modifica al modello:
1. `lo = max(2.5, 0.004*w)` (era `0.015*w`): a w=848 il minimo scende a 3.4 px e i neri veri entrano.
2. guardia sull'indice nella mappatura note: `note[i] = ordine[j] if 0 <= j < len(ordine) else None`
   + `continue` nel ciclo `src/dst`. Era un **bug latente**: con più run rilevati dei 36 neri del
   modello (36..96) la lista andava in `IndexError: list index out of range`.

| | prima | dopo |
|---|---|---|
| inlier (frame 0 / serie) | 0 / 0 | **162 / 208–226** |
| tasti inquadrati | 19 (48..66) | **61 (36..96)** |
| evidenza | 0.82–0.89 | 0.48–0.52 |
| eventi / note uniche | 15 / 10 | 33 / 14 |

Verifica indipendente che la griglia **cade sui tasti** (da `griglia.json`, per ognuno dei 25 neri del
modello: distanza fra centro cella e centro del run scuro reale più vicino, frame 0/60/120/180):
mediana **0.4–0.8 px**, p90 ≤ 1.3, max 2.2, **identica sui tre terzi** (sx 0.3–0.5 / centro 0.6–1.1 /
dx 0.4–0.8) → nessuna deriva ai bordi. Per confronto, sul video verticale che funziona: mediana
0.4–1.1 ma max fino a 7.0 px. La scala compressa dell'ancora (9.3 px) viene **recuperata** da
`affina`/tracking.

Non-regressione (ancora sul frame 0; varianti = originale / sola guardia / fix applicato):

| video | originale | sola guardia | fix |
|---|---|---|---|
| b2 848×464 | 76.4 px, 0 inl | 76.4 px, 0 inl | 9.3 px, **162 inl** |
| verticale 720×1280 | 51.9 px, 76 inl | 51.9 px, 76 inl | 51.9 px, 76 inl |
| test_shotA 1280×720 | 40.4 px, 118 inl | 40.4 px, 118 inl | 40.3 px, **137 inl** |
| test_shotC 1280×720 | 32.2 px, 70 inl | 32.2 px, 70 inl | 32.2 px, 69 inl |
| demo_video 1280×720 | 40.4 px, 118 inl | 40.4 px, 118 inl | 40.3 px, **137 inl** |

- la guardia da sola è **inerte** (identica all'originale ovunque): è una rete di sicurezza, non un fix;
- il filtro permissivo **migliora** anche shotA/demo (118 → 137 inlier); shotC perde 1 inlier (rumore);
- sul video verticale l'ancora è identica (51.9/76) e gli eventi finali cambiano di poco: **53/20 vs
  52/21** (un G#4 in meno, 2 note ±1 semitono) perché il re-ancoraggio per-frame parte da una H0
  lievemente diversa. Se servisse l'identità bit-per-bit su quel video, la variante "filtro stretto
  prima, permissivo **solo se** i neri scarseggiano nel frame" la garantisce, ma perde il guadagno
  118 → 137 su shotA/demo;
- `demo_video` (stacchi veri ai frame 122 e 242): 44 eventi/40 note vs 38/36, stessa gamma 36..91; gli
  eventi in più stanno sui frame dello stacco (rumore già noto, non un comportamento nuovo).

Cosa **non** era il problema (misurato e scartato):
- **la finestra di ricerca del passo** (`s_lo = w/60`): allargarla a `w/200` **non cambia nulla** su b2
  — la NCC al passo vero (10.2 px) vale 0.047 e il massimo resta 76.75 px in entrambe le finestre.
  Neutra sui video che già funzionano.
- il crop 600×120 funzionava non perché i tasti fossero più grandi, ma perché **toglie le colonne
  non-tastiera** e `_bande_righe` sceglie le righe dei neri: con un crop da 700 px (finestra 11.7..70,
  passo vero fuori finestra) il motore aggancia 69.25 px. Non è una strada robusta.

Resta aperto (nuovo):
- **copertura**: il modello copre `NOTA_MIN..NOTA_MAX = 36..96` (C2..C7, 61 tasti) mentre in b2 è
  inquadrato il pianoforte intero (A0..C8, 88 tasti): le note fuori da C2..C7 non sono rappresentabili
  (nel clip b2 le note emesse sono 39..64, quindi dentro; altri clip dello stesso video le
  perderebbero). Portare le due costanti a 21..108 è meccanicamente possibile — i riquadri in
  `sagome.json` si generano dalla griglia e `u_nero`/`_indice_bianco`/`e_nero` sono generici — ma è un
  cambio di modello: da provare a parte. → **provato e applicato: §5.3**.
- **identità della nota**: il nome assoluto dipende dall'assunzione "il gruppo da DUE neri più vicino
  al centro del frame è C#4–D#4" (`nota_gruppo2=61`, correggibile con `--nota-gruppo2`/`--prima-nota`).
  La geometria dice **quale tasto**; **quale nota** va confermato a mano quando la tastiera inquadrata
  non è quella attesa. → **misurato e corretto: §5.3**.
- **scala dell'ancora**: sul frame 0 resta compressa (**9.3 px contro ~10.5 misurati**, -11%): la
  recupera `affina`, ma la causa probabile è che `piccolo/1.15` risente dei run spuri (40 rilevati
  contro 36 neri veri). Una stima del passo dal **periodo d'ottava** del pattern dei neri
  (autocorrelazione dei centri) sarebbe scale-free e robusta a qualche run spuro.

### 5.3 Chiusura dei due punti aperti di §5.2: copertura (88 tasti) e ottava (centro tastiera)

Guardando b2 l'utente ha detto: *"quasi metà pianoforte non viene sgamato (la metà sinistra)"*. La
misura dice esattamente perché: **non era un problema di rilevazione, era il lessico del modello
(61 tasti) più l'ottava dell'ancora (riferita al frame, non alla tastiera)**.

**Cosa si vede nell'immagine, misurato senza il modello**
- riga dei neri: 34-36 blob scuri **alti** (campitura 17 righe, larghezza 5-10 px) a **x 140..631**;
  i gap fra neri consecutivi valgono 1.2 e 1.78 passi bianchi (gli offset `_NERI_PC`) e il pattern
  `[2,1,2,1,1]` si ripete → il primo nero (x=140) è di **tipo A#**;
- la tastiera inquadrata è un **88 tasti completo**: A0 a **x≈125-128**, C8 a **x≈650**, 52 passi
  bianchi ≈ 10.0 px (una tastiera parziale avrebbe 25 o 31 neri, non 34-36);
- il modello (61 tasti) disegnava i suoi neri a **x 308..633** e le celle a **x 301..652**:
  restavano fuori 11 neri e ~15 bianchi a sinistra (≈2.7 ottave) — cioè il bordo sinistro che
  l'utente vedeva senza griglia.

**Le due cause (indipendenti, entrambe necessarie)**
1. `NOTA_MIN..NOTA_MAX = 36..96` (C2..C7, 61 tasti): i tasti fuori finestra **non esistono nel
   lessico**, quindi a sinistra non poteva esserci griglia (e l'ancora stessa li scarta: il guard
   di §5.2 li mappa a `None`).
2. l'ottava dell'ancora si sceglieva con il gruppo da DUE neri più vicino al **centro del frame**
   (`w/2`): in b2 il pianoforte è decentrato (tastiera 125..650, centro 388; frame 424) e il gruppo
   più vicino al centro del frame è **C#5-D#5** invece di C#4-D#4 → *tutte* le etichette uscivano
   **12 semitoni basse**. Prova: il nero reale a x=140 è di tipo A# (pattern) e il modello lo
   chiamava `A#-1` → +12 = `A#0`.

**Fix applicato (`griglia_prospettica.py`, due modifiche, nessun flag nuovo)**
- `NOTA_MIN, NOTA_MAX = 21, 108` (A0..C8), come già fanno `sagome.py` (`nota_min=21,
  nota_max=108`) e `to_midi.py`: il modello torna coerente con il resto del progetto;
- in `_H_iniziale_classico` l'ottava si ancora al **centro della tastiera**: dai neri rilevati si
  prende lo span *regolare* (si tagliano i blob fuori tastiera: buchi ≥3.6 passi non sono tasti) e
  si usa `xc_tast = (primo+ultimo)/2` al posto di `w/2`.

**Verifica su b2 (frame 0 e corsa completa)**
| | prima (36..96) | dopo (21..108) |
|---|---|---|
| inlier frame 0 | 162 | **228** |
| tasti inquadrati | 61 | **88** |
| celle nella zona vera dei bianchi | 36/36 | **52/52** |
| celle x | 301..652 | **125..650** (= la tastiera) |
| primo nero del modello | C#2 (x 308) | **A#0 (x 140)** |
| note inquadrate / emesse | 61 / 14 | **88 / 24** |
| intervallo MIDI emesso | 39..71 | **21..83** |

Eventi 33 → **47**. Delle 14 note emesse prima, **12 ricompaiono identiche trasposte di +12
semitoni** (18 eventi anche nello stesso istante): la melodia era letta un'ottava sotto. Le note
nuove sono **la mano sinistra**: F#2 (0.40 s), A0 (0.64/0.77), B1 (0.77), A1 (0.80), G1 (0.87),
A#3 (1.07), C2+C#2 (1.37), A#1 (1.71), C2 (3.92), D2 (4.49), B1 (7.27) — prima non esistevano.

**Regressione (ancora sul frame 0, `/tmp/prova_ancora_88.py`)**
| video | orig | fix §5.2 | **progetto ora** |
|---|---|---|---|
| b2 (lontana) | 76.4 / 0 inl / 0/36 celle | 9.3 / 162 / 36/36 | **9.6 / 228 / 52/52** |
| verticale | 51.9 / 76 | 51.9 / 76 | **51.9 / 76** (identico) |
| test_shotA | 40.4 / 118 | 40.3 / 137 | **40.3 / 137** (identico) |
| test_shotC | 32.2 / 70 | 32.2 / 69 | **32.2 / 81** |
| demo_video | 40.4 / 118 | 40.3 / 137 | **40.3 / 137** (identico) |

E la corsa completa sul **video verticale** (il caso che funzionava) è **identica**: 22 tasti,
note 53..74, **53 eventi / 20 note** con le stesse note. Su `demo_video` (stacchi veri ai frame
122/242) la corsa vede più tasti dopo i tagli (61→77 inquadrate, 40→44 note): le differenze stanno
sui bordi della gamma, dove prima il modello non arrivava.

**Come ricontrollare in mezzo minuto**
- `python3 /tmp/ancora_b2.py griglia_prospettica.py` → deve stampare `NOTA_MIN..MAX = 21..108`,
  `inlier affina = 228`, `celle in frame: 88  x 125..650`, `celle più a sinistra: A0 (21)`;
- `python3 /tmp/copertura.py <run> <video>` → i neri del modello (x 140..631) devono coprire i
  neri reali e non restare nulla fuori a sinistra (i residui erano blob non-tastiera);
- guardare `prima_griglia.jpg`: le etichette partono da **A0** e la griglia copre tutta la tastiera.

**Resta aperto dopo §5.3**
- l'ottava si decide ancora con un'euristica ("il gruppo da 2 neri più vicino al centro della
  tastiera è C#4-D#4"): giusta quando la tastiera intera è inquadrata e centrata su se stessa,
  equivalente al comportamento di prima quando la vista è parziale (video verticale). Il criterio
  robusto è quello del progetto fratello `pianovam-video2midi/src/detect.py`: far combaciare i
  **bordi** della tastiera del modello (A0, C8) con i bordi verticali della tastiera nell'immagine
  (il pattern dei neri si ripete ogni 12 tasti, i bordi no). Da fare se arrivano video con tastiera
  parziale *e* decentrata.
- con il modello a 88 tasti, su un video con tastiera **più corta di 88 tasti** (es. synth 61 tasti)
  le celle dei tasti in più cadranno fuori dalla tastiera e verranno comunque campionate: da
  misurare su un video così (nessuno nei test attuali: i 5 video hanno tastiera intera o parziale
  centrata).
- la scala dell'ancora al frame 0 resta compressa (`piccolo/1.15`, §5.2): invariata.


---

## 6. Mappa dei file del progetto

| file | ruolo | in §7? |
|---|---|---|
| `piano_detector.py` | stadio 1 (YOLOv8): rileva il pianoforte/tastiera | sì |
| `keyboard_grid.py` | modello geometrico dei 88 tasti (offset neri, omografia) | sì |
| `keyboard_tracker.py` | inseguimento del riquadro tastiera tra i frame | sì |
| `hands.py` | hand landmarker (mediapipe) | no |
| `note_events.py` | pressioni → eventi nota (isteresi) | no |
| `to_midi.py` | `notes.json` / `song.mid` (pretty_midi) | no |
| `pipeline.py` | motore `pipeline` (YOLO + mani) | no |
| `ppan_bridge.py` | converte l'uscita di PPAN | no |
| `motore_calibrato.py` | motore `calibrato` (sagome) + decisione premuto | sì |
| `sagome.py` | misura tasti / riquadri per nota (il difetto storico) | sì |
| `motore_prospettica.py` | motore `prospettica` (nuovo) | sì |
| `griglia_prospettica.py` | stima geometrica della griglia dei tasti (cuore del nuovo motore) | sì |
| `pipeline_web.py` | server Flask dello Studio (porta 7862, rotte, coda job) | no (su richiesta) |
| `pipeline_studio.html`, `video_viewer.html` | frontend (non indispensabili qui) | no |
| `app.py`, `video_app.py`, `gen_test.py`, `test_sagome.py` | UI/strumenti secondari | no |

---

## 7. Codice essenziale

Qui sotto, i moduli chiave così come sono adesso (versione corrente). Gli altri file sono
disponibili su richiesta.


### `piano_detector.py`

````python
"""
Piano Detector — rileva il riquadro del pianoforte in un'immagine/frame.

Modello: YOLOv8 (Open Images V7) — classi usate: "Piano" e "Musical keyboard".
Pensato per essere il primo stadio di una pipeline video -> MIDI:
    frame -> detect_piano() -> crop -> (stadi successivi: tasti, mani, note)

Uso come libreria:
    from piano_detector import PianoDetector
    det = PianoDetector("weights/yolov8l-oiv7.pt")
    box = det.detect_piano("frame.jpg")          # -> PianoBox | None
    crop = det.crop_piano("frame.jpg", "out.jpg")

Uso da riga di comando:
    python piano_detector.py immagine.jpg -o output/
    python piano_detector.py *.jpg --conf 0.10 --all
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

# Classi Open Images V7 considerate
CLASSI_TARGET = ("piano", "musical keyboard")
COLORE_PIANO = (36, 200, 80)      # verde (BGR)
COLORE_KEYBOARD = (255, 170, 30)  # azzurro (BGR)


@dataclass
class PianoBox:
    """Risultato della rilevazione."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidenza: float
    classe: str  # "piano" oppure "musical keyboard"

    @property
    def larghezza(self) -> int:
        return self.x2 - self.x1

    @property
    def altezza(self) -> int:
        return self.y2 - self.y1


class PianoDetector:
    """Rileva il pianoforte in immagini o frame video (np.ndarray BGR)."""

    def __init__(self, pesi: str = "weights/yolov8l-oiv7.pt",
                 conf: float = 0.15, iou: float = 0.5, device: str | None = None):
        self.model = YOLO(pesi)
        self.conf = conf
        self.iou = iou
        self.device = device
        # id numerici delle classi target nel modello
        self._ids = [i for i, n in self.model.names.items()
                     if n.lower() in CLASSI_TARGET]
        if not self._ids:
            raise RuntimeError("Classi 'piano'/'musical keyboard' non trovate nel modello.")

    # ------------------------------------------------------------------ API
    def detect_all(self, immagine) -> list[PianoBox]:
        """Tutte le rilevazioni (piano + tastiere), ordinate per confidenza."""
        img = self._carica(immagine)
        res = self.model.predict(img, classes=self._ids, conf=self.conf,
                                 iou=self.iou, verbose=False, device=self.device)[0]
        h, w = img.shape[:2]
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            out.append(PianoBox(
                x1=max(0, int(x1)), y1=max(0, int(y1)),
                x2=min(w, int(x2)), y2=min(h, int(y2)),
                confidenza=round(float(b.conf), 3),
                classe=self.model.names[int(b.cls)].lower(),
            ))
        out.sort(key=lambda d: d.confidenza, reverse=True)
        return out

    def detect_piano(self, immagine, margine: float = 0.0) -> PianoBox | None:
        """
        Il riquadro migliore del pianoforte.
        Preferenza: classe 'piano' (strumento intero); se assente, si ripiega
        su 'musical keyboard' (utile nei primi piani sui tasti).
        `margine`: frazione (0-1) di padding attorno al box, es. 0.05 = 5%.
        """
        dets = self.detect_all(immagine)
        if not dets:
            return None
        piani = [d for d in dets if d.classe == "piano"]
        best = piani[0] if piani else dets[0]
        if margine > 0:
            best = self._espandi(best, immagine, margine)
        return best

    def crop_piano(self, immagine, out_path: str | None = None,
                   margine: float = 0.0) -> np.ndarray | None:
        """Restituisce (e opzionalmente salva) il ritaglio del pianoforte."""
        img = self._carica(immagine)
        box = self.detect_piano(img, margine=margine)
        if box is None:
            return None
        crop = img[box.y1:box.y2, box.x1:box.x2]
        if out_path:
            cv2.imwrite(out_path, crop)
        return crop

    def annota(self, immagine, out_path: str | None = None,
               margine: float = 0.0) -> np.ndarray:
        """Disegna il box scelto (verde) e le altre rilevazioni (azzurro)."""
        img = self._carica(immagine).copy()
        dets = self.detect_all(img)
        best = self.detect_piano(img, margine=margine)
        for d in dets:
            e_best = best and (d.x1, d.y1, d.x2, d.y2) == (best.x1, best.y1, best.x2, best.y2)
            colore = COLORE_PIANO if e_best else COLORE_KEYBOARD
            spessore = 3 if e_best else 1
            cv2.rectangle(img, (d.x1, d.y1), (d.x2, d.y2), colore, spessore)
            label = f"{d.classe} {d.confidenza:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(img, (d.x1, d.y1 - th - 10), (d.x1 + tw + 6, d.y1), colore, -1)
            cv2.putText(img, label, (d.x1 + 3, d.y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        if out_path:
            cv2.imwrite(out_path, img)
        return img

    # -------------------------------------------------------------- interni
    @staticmethod
    def _carica(immagine) -> np.ndarray:
        if isinstance(immagine, np.ndarray):
            return immagine
        img = cv2.imread(str(immagine))
        if img is None:
            raise ValueError(f"Immagine non leggibile: {immagine}")
        return img

    def _espandi(self, box: PianoBox, immagine, margine: float) -> PianoBox:
        img = self._carica(immagine)
        h, w = img.shape[:2]
        dx, dy = int(box.larghezza * margine), int(box.altezza * margine)
        return PianoBox(
            x1=max(0, box.x1 - dx), y1=max(0, box.y1 - dy),
            x2=min(w, box.x2 + dx), y2=min(h, box.y2 + dy),
            confidenza=box.confidenza, classe=box.classe,
        )


# ---------------------------------------------------------------------- CLI
def main(argv=None):
    p = argparse.ArgumentParser(description="Rileva il pianoforte in un'immagine.")
    p.add_argument("immagini", nargs="+", help="immagine/i di input")
    p.add_argument("-o", "--output", default="output", help="cartella di output")
    p.add_argument("-w", "--weights", default="weights/yolov8l-oiv7.pt")
    p.add_argument("--conf", type=float, default=0.15, help="soglia di confidenza")
    p.add_argument("--margine", type=float, default=0.0,
                   help="padding attorno al box, frazione 0-1 (es. 0.05)")
    p.add_argument("--all", action="store_true",
                   help="salva il crop di OGNI rilevazione, non solo la migliore")
    args = p.parse_args(argv)

    det = PianoDetector(args.weights, conf=args.conf)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in args.immagini:
        stem = Path(path).stem
        try:
            box = det.detect_piano(path, margine=args.margine)
        except ValueError as e:
            print(e, file=sys.stderr)
            continue

        det.annota(path, str(out_dir / f"{stem}_annotata.jpg"), margine=args.margine)
        if box is None:
            print(f"{path}: nessun pianoforte rilevato")
            continue

        img = det._carica(path)
        cv2.imwrite(str(out_dir / f"{stem}_crop.jpg"),
                    img[box.y1:box.y2, box.x1:box.x2])
        print(json.dumps({"immagine": path, "riquadro_scelto": asdict(box)},
                         ensure_ascii=False))

        if args.all:
            for i, d in enumerate(det.detect_all(path)):
                cv2.imwrite(str(out_dir / f"{stem}_crop_{i}_{d.classe}.jpg"),
                            img[d.y1:d.y2, d.x1:d.x2])


if __name__ == "__main__":
    main()

````

### `keyboard_grid.py`

````python
"""
Keyboard Grid — geometria dei tasti dentro il riquadro/quadrilatero della tastiera.

Stadio 2 / E3 della pipeline video -> MIDI.

MODELLO GEOMETRICO (formule esatte)
-----------------------------------
Si lavora in uno spazio canonico unitario (u, v):
    u in [0, 1]  asse della tastiera, dal tasto piu' grave al piu' acuto
    v in [0, 1]  profondita' del tasto, v=0 bordo superiore (lato dei neri),
                 v=1 bordo frontale (verso il suonatore)
Il quadrilatero della tastiera nel frame (TL, TR, BR, BL) e' il trasformato
del quadrato unitario tramite un'omografia (cv2.getPerspectiveTransform):
tutto cio' che segue e' calcolato in (u, v) e riportato nel frame con l'omografia.

  * n_b = numero di tasti bianchi; ogni bianco i occupa
        u in [i/n_b, (i+1)/n_b],  v in [0, 1].
  * Un nero di numero MIDI N ha il bianco sottostante (N-1) di indice i, quindi
    il confine fra i due bianchi adiacenti e' u_c = (i+1)/n_b. Il suo centro e'
        u_nero = u_c + offset[N % 12] / n_b
    con offset (in larghezze di tasto bianco) tratto dalla disposizione reale:
        C#: -0.10   D#: +0.10   F#: -0.12   G#: 0.00   A#: +0.12
    (C#/F# lievemente a sinistra, D#/A# a destra, G# centrato: sono
    approssimazioni di misure tipiche, errore < ~0.03 larghezze di bianco.)
  * Larghezza del nero = larghezza_neri / n_b (cioe' 0.60 larghezze di bianco).
  * Lunghezza del nero: occupa v in [0, altezza_bianchi]. NOTA: il brief la
    descriveva come "1 - altezza_bianchi", ma con il default 0.62 darebbe 0.38,
    fisicamente troppo corta (i neri reali sono ~0.62-0.65 dei bianchi). Qui
    `altezza_bianchi` e' quindi la frazione di profondita' coperta dai neri.

nota_a() ignora i punti fuori dalla tastiera e, in sovrapposizione, da' priorita'
al NERO (e' disegnato sopra le due porzioni di bianco adiacenti).

ASSUNZIONI DI ORIENTAMENTO: tasti gravi a sinistra, lato dei neri (retro della
tastiera) verso l'alto dell'immagine. Se il video e' capovolto la griglia va
girata a monte: controllare `prima_griglia.jpg`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

NOMI_NOTE = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_NERI_PC = frozenset({1, 3, 6, 8, 10})
_OFFSET_NERI = {1: -0.10, 3: 0.10, 6: -0.12, 8: 0.0, 10: 0.12}

MIDI_MIN, MIDI_MAX = 21, 108          # A0 .. C8 (pianoforte a 88 tasti)
LARGHEZZA_BIANCO_CM = 2.2             # assunzione per stima_estensione
LUNGHEZZA_BIANCO_CM = 15.0            # assunzione per stima_estensione
_N_BIANCHI_88 = 52
_QUADRATO = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])


def nome_nota(n: int) -> str:
    """Notazione scientifica: MIDI 60 -> 'C4', 21 -> 'A0'."""
    return f"{NOMI_NOTE[n % 12]}{n // 12 - 1}"


def e_nero(n: int) -> bool:
    return (n % 12) in _NERI_PC


@dataclass
class Tasto:
    nota: int          # numero MIDI (A0 = 21, C8 = 108)
    nome: str          # "C4", "F#3", ...
    nero: bool
    poligono: list[tuple[float, float]]   # 4 vertici nel frame originale


class KeyboardGrid:
    """Griglia dei tasti costruita sul riquadro (o quadrilatero) della tastiera."""

    def __init__(self, prima_nota: int = 21, n_ottave: int = 7,
                 altezza_bianchi: float = 0.62, larghezza_neri: float = 0.60,
                 prospettiva: bool = True, ultima_nota: int | None = None) -> None:
        """
        prima_nota / n_ottave: estensione = da prima_nota a prima_nota + 12*n_ottave
            (inclusa), limitata a 21..108. `ultima_nota` (opzionale) la sostituisce.
        Gli estremi vengono portati su tasti bianchi (un nero non puo' stare al
        bordo): prima_nota nero -> scende di 1; ultima_nota nero -> sale di 1.
        Gli attributi `prima_nota` / `ultima_nota` riportano i valori effettivi.
        """
        if not 0.0 < altezza_bianchi <= 1.0:
            raise ValueError("altezza_bianchi deve essere in (0, 1]")
        if not 0.0 < larghezza_neri < 1.0:
            raise ValueError("larghezza_neri deve essere in (0, 1)")
        self.altezza_bianchi = float(altezza_bianchi)
        self.larghezza_neri = float(larghezza_neri)
        self.prospettiva = bool(prospettiva)

        prima = int(min(max(prima_nota, MIDI_MIN), MIDI_MAX))
        ultima = int(ultima_nota) if ultima_nota is not None \
            else prima + int(round(12 * n_ottave))
        ultima = int(min(max(ultima, MIDI_MIN), MIDI_MAX))
        if e_nero(prima):
            prima -= 1
        if e_nero(ultima):
            ultima += 1
        prima, ultima = max(prima, MIDI_MIN), min(ultima, MIDI_MAX)
        if ultima - prima < 2:
            raise ValueError(f"estensione troppo piccola: {prima}..{ultima}")
        self.prima_nota, self.ultima_nota = prima, ultima

        note = list(range(prima, ultima + 1))
        self._bianchi = [n for n in note if not e_nero(n)]
        self.n_bianchi = len(self._bianchi)
        indice = {n: i for i, n in enumerate(self._bianchi)}
        nb = self.n_bianchi
        self._neri: list[tuple[int, float, float]] = []   # (nota, u_centro, semi-larghezza)
        hw = self.larghezza_neri / (2.0 * nb)
        for n in note:
            if e_nero(n):
                uc = (indice[n - 1] + 1) / nb + _OFFSET_NERI[n % 12] / nb
                self._neri.append((n, uc, hw))
        self._note = note

        # poligoni nello spazio canonico (u, v) per ogni nota, ordinati come _note
        self._poligoni_unit: list[np.ndarray] = []
        neri = {n: (uc, h) for n, uc, h in self._neri}
        for n in note:
            if e_nero(n):
                uc, h = neri[n]
                p = [(uc - h, 0.0), (uc + h, 0.0), (uc + h, self.altezza_bianchi),
                     (uc - h, self.altezza_bianchi)]
            else:
                i = indice[n]
                p = [(i / nb, 0.0), ((i + 1) / nb, 0.0), ((i + 1) / nb, 1.0), (i / nb, 1.0)]
            self._poligoni_unit.append(np.float32(p))

        self._M: np.ndarray | None = None      # canonico -> frame
        self._Minv: np.ndarray | None = None   # frame -> canonico
        self._dim = (1.0, 1.0)                 # (larghezza, altezza) del quad in px
        self.info_stima: dict = {}

    # ------------------------------------------------------------------ API
    def costruisci(self, traccia: "Traccia", frame_shape: tuple[int, int]) -> list[Tasto]:
        """Costruisce i tasti sulla traccia; aggiorna lo stato usato da nota_a()."""
        h, w = frame_shape[:2]
        quad = self._quad_da_traccia(traccia)
        quad[:, 0] = np.clip(quad[:, 0], 0, max(0, w - 1))
        quad[:, 1] = np.clip(quad[:, 1], 0, max(0, h - 1))
        lw, lh = self._lati(quad)
        if lw < 2.0 or lh < 2.0:
            raise ValueError("riquadro della tastiera degenere")
        self._M = cv2.getPerspectiveTransform(_QUADRATO, quad)
        self._Minv = np.linalg.inv(self._M)
        self._dim = (lw, lh)

        tutti = np.concatenate(self._poligoni_unit).reshape(-1, 1, 2).astype(np.float32)
        nel_frame = cv2.perspectiveTransform(tutti, self._M).reshape(-1, 4, 2)
        return [Tasto(nota=n, nome=nome_nota(n), nero=e_nero(n),
                      poligono=[(float(x), float(y)) for x, y in nel_frame[i]])
                for i, n in enumerate(self._note)]

    def punto_raddrizzato(self, punto: tuple[float, float]) -> tuple[float, float]:
        """(x, y) del frame -> (u, v) canonici (u lungo la tastiera, v in profondita', 0-1 dentro i tasti)."""
        if self._Minv is None:
            raise RuntimeError("chiamare costruisci() prima di usare la griglia")
        x, y = float(punto[0]), float(punto[1])
        p = self._Minv @ np.array([x, y, 1.0])
        if abs(p[2]) < 1e-12:
            return float("nan"), float("nan")
        return float(p[0] / p[2]), float(p[1] / p[2])

    def nota_a(self, punto: tuple[float, float], margine_px: float = 0.0) -> int | None:
        """Nota MIDI sotto il punto (x, y) del frame, None se fuori dai tasti (entro il margine)."""
        u, v = self.punto_raddrizzato(punto)
        if not (math.isfinite(u) and math.isfinite(v)):
            return None
        lw, lh = self._dim
        mu, mv = margine_px / lw, margine_px / lh
        if u < -mu or u > 1 + mu or v < -mv or v > 1 + mv:
            return None
        u = min(max(u, 0.0), 1.0)
        v = min(max(v, 0.0), 1.0)

        # i neri hanno priorita': scelgo quello piu' vicino fra i candidati
        migliore, dist = None, 1e9
        for nota, uc, hw in self._neri:
            d = abs(u - uc)
            if d <= hw + mu and v <= self.altezza_bianchi + mv and d < dist:
                migliore, dist = nota, d
        if migliore is not None:
            return migliore
        i = min(int(u * self.n_bianchi), self.n_bianchi - 1)
        return self._bianchi[i]

    def frame_raddrizzato(self, frame: np.ndarray, traccia: "Traccia",
                          larghezza: int = 1200) -> tuple[np.ndarray, np.ndarray]:
        """Tastiera vista di fronte: -> (immagine raddrizzata, omografia 3x3 frame -> immagine)."""
        quad = self._quad_da_traccia(traccia)
        lw, lh = self._lati(quad)
        wd = max(1, int(larghezza))
        hd = max(1, int(round(wd * lh / lw)))
        dst = np.float32([[0, 0], [wd, 0], [wd, hd], [0, hd]])
        M = cv2.getPerspectiveTransform(quad, dst)
        return cv2.warpPerspective(frame, M, (wd, hd)), M

    def stima_estensione(self, traccia: "Traccia", larghezza_frame: int) -> tuple[int, int]:
        """
        Propone (prima_nota, ultima_nota) visibili. E' una STIMA, non una misura.

        Assunzioni (da verificare):
          1. il box copre la profondita' dei tasti bianchi (~15 cm) e la sua
             larghezza copre n tasti bianchi da ~2.2 cm, quindi
             n_bianchi = (larghezza_px / altezza_px) * (15.0 / 2.2) ~ 6.8 * w/h;
          2. la finestra visibile e' CENTRATA sul centro del pianoforte a 88
             tasti (fra E4 e F4).
        Errore atteso: n_bianchi +-15% (qualche tasto ai bordi); l'assunzione 2 e'
        quella pericolosa: se l'inquadratura non e' centrata, TUTTE le note sono
        trasposte (tipicamente di una o piu' ottave). Il numero di tasti e'
        affidabile, l'ottava assoluta NO: va fornita a mano (prima_nota).
        `larghezza_frame` serve solo a segnalare in `info_stima['taglio_frame']`
        che il box tocca i bordi (tastiera probabilmente tagliata: stima per difetto).
        """
        quad = self._quad_da_traccia(traccia)
        lw, lh = self._lati(quad)
        grezzo = (lw / lh) * (LUNGHEZZA_BIANCO_CM / LARGHEZZA_BIANCO_CM)
        n_b = int(min(max(round(grezzo), 7), _N_BIANCHI_88))
        primo = int(min(max(math.floor(26 - n_b / 2), 0), _N_BIANCHI_88 - n_b))
        bianchi_88 = [n for n in range(MIDI_MIN, MIDI_MAX + 1) if not e_nero(n)]
        prima, ultima = bianchi_88[primo], bianchi_88[primo + n_b - 1]
        self.info_stima = {
            "n_bianchi_grezzo": round(float(grezzo), 2),
            "n_bianchi": n_b,
            "prima_nota": prima,
            "ultima_nota": ultima,
            "taglio_frame": bool(larghezza_frame and
                                 (traccia.x1 <= 2 or traccia.x2 >= larghezza_frame - 2)),
        }
        return prima, ultima

    # -------------------------------------------------------------- interni
    def _quad_da_traccia(self, traccia) -> np.ndarray:
        quad = getattr(traccia, "quad", None)
        if self.prospettiva and quad is not None and len(quad) == 4:
            return np.float32(quad).reshape(4, 2).copy()
        return np.float32([[traccia.x1, traccia.y1], [traccia.x2, traccia.y1],
                           [traccia.x2, traccia.y2], [traccia.x1, traccia.y2]])

    @staticmethod
    def _lati(quad: np.ndarray) -> tuple[float, float]:
        """(larghezza, altezza) medie del quad in px."""
        larg = 0.5 * (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3]))
        alt = 0.5 * (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1]))
        return float(larg), float(alt)

````

### `keyboard_tracker.py`

````python
"""
Keyboard Tracker — segue il riquadro della tastiera fra i frame di un video.

Stadio 2 / E1 della pipeline video -> MIDI.

Strategia: la rete neurale (PianoDetector) gira solo sul 1° frame, poi
periodicamente (ogni `intervallo_redetect` frame) e, in modo forzato, quando il
tracking perde il bersaglio (somiglianza sotto soglia). Nei frame intermedi si
usa un tracker leggero:

  * tracker="template": template matching (cv2.matchTemplate, TM_CCOEFF_NORMED)
    in una finestra di ricerca attorno alla posizione precedente. Non dipende da
    il modulo legacy di OpenCV ne' da file di modello esterni.
  * tracker="mil": cv2.TrackerMIL_create() (presente in OpenCV 5). Se non e'
    disponibile si ripiega automaticamente su "template" con un warning.

Per la geometria dei tasti si usa la classe 'musical keyboard' (i tasti), con
'piano' (strumento intero) solo come ripiego: e' l'opposto di
PianoDetector.detect_piano(), che qui NON viene usato.

In piu' del contratto minimo, `Traccia` porta un campo opzionale `quad` (4
vertici TL,TR,BR,BL nel frame) stimato con una raffinazione prudente del box:
serve a KeyboardGrid per la prospettiva. Se la raffinazione non e' affidabile
vale None e la griglia usa il rettangolo.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:  # solo per i type hint: nessun import di ultralytics qui
    from piano_detector import PianoDetector

CLASSE_PREFERITA = "musical keyboard"

_SCALA_LAVORO = 0.5          # i frame sono ridotti a meta' per il template matching
_DIM_MIN = 16                # lato minimo (px) di un box valido
_RETRY_PERSO = 5             # ogni quanti frame ritentare la rilevazione se si e' persi
_AGG_TEMPLATE_OGNI = 5       # il template si aggiorna al massimo ogni N frame...
_SOGLIA_AGG_TEMPLATE = 0.75  # ...e solo se la somiglianza e' alta
_ALFA_TEMPLATE = 0.15        # peso del nuovo patch nell'EMA del template


@dataclass
class Traccia:
    """Riquadro della tastiera in un frame."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidenza: float          # confidenza "di tracciamento" 0-1
    origine: str               # "detector" | "tracker"
    frame: int
    quad: list[tuple[float, float]] | None = None  # TL, TR, BR, BL (opzionale)

    @property
    def larghezza(self) -> int:
        return self.x2 - self.x1

    @property
    def altezza(self) -> int:
        return self.y2 - self.y1


# ----------------------------------------------------------------- utilita'
def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    unione = area_a + area_b - inter
    return inter / unione if unione > 0 else 0.0


def _clamp_box(box, w: int, h: int):
    """Porta il box (float) dentro il frame mantenendo una dimensione minima."""
    x1, y1, x2, y2 = box
    x1 = min(max(0.0, x1), w - _DIM_MIN)
    y1 = min(max(0.0, y1), h - _DIM_MIN)
    x2 = min(max(x1 + _DIM_MIN, x2), float(w))
    y2 = min(max(y1 + _DIM_MIN, y2), float(h))
    return [x1, y1, x2, y2]


def _grigio(frame: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return cv2.resize(g, None, fx=_SCALA_LAVORO, fy=_SCALA_LAVORO,
                      interpolation=cv2.INTER_AREA)


def _ordina_quad(pts: np.ndarray):
    """Ordina 4 punti come TL, TR, BR, BL. None se degenerati."""
    s = pts.sum(axis=1)
    d = pts[:, 1] - pts[:, 0]
    idx = [int(np.argmin(s)), int(np.argmin(d)), int(np.argmax(s)), int(np.argmax(d))]
    if len(set(idx)) != 4:
        return None
    return pts[idx]


def _raffina_quad(frame: np.ndarray, box) -> list[tuple[float, float]] | None:
    """
    Stima prudente dei 4 vertici della tastiera dentro il box del detector.

    Soglia Otsu sul ritaglio, chiusura morfologica (riempie i tasti neri),
    contorno piu' grande -> poligono a 4 lati. Il risultato e' accettato solo se
    e' vicino al box (ogni vertice entro il 15% della larghezza e il 20%
    dell'altezza dal corrispondente angolo del box) e copre almeno il 60% della
    sua area: serve solo a correggere una prospettiva lieve, mai a inventare una
    forma. In ogni altro caso ritorna None (e la griglia usa il rettangolo).
    """
    H, W = frame.shape[:2]
    x1, y1 = max(0, int(round(box[0]))), max(0, int(round(box[1])))
    x2, y2 = min(W, int(round(box[2]))), min(H, int(round(box[3])))
    bw, bh = x2 - x1, y2 - y1
    if bw < _DIM_MIN * 4 or bh < _DIM_MIN * 2:
        return None
    roi = frame[y1:y2, x1:x2]
    g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    g = cv2.GaussianBlur(g, (5, 5), 0)
    _, bin_ = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = max(5, int(0.05 * min(bw, bh))) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    area_box = float(bw * bh)

    candidato, miglior_score = None, 0.0
    for img in (bin_, 255 - bin_):
        chiuso = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)
        contorni, _ = cv2.findContours(chiuso, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contorni:
            continue
        c = max(contorni, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area < 0.35 * area_box:
            continue
        hull = cv2.convexHull(c)
        area_hull = cv2.contourArea(hull)
        if area_hull <= 0:
            continue
        score = (area / area_box) * (area / area_hull)
        if score <= miglior_score:
            continue
        pts = None
        peri = cv2.arcLength(hull, True)
        for f in (0.01, 0.02, 0.03, 0.05, 0.08):
            approx = cv2.approxPolyDP(hull, f * peri, True)
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)
                break
        if pts is None:
            try:
                pts = cv2.boxPoints(cv2.minAreaRect(hull)).astype(np.float32)
            except (AttributeError, cv2.error):
                continue
        ordinati = _ordina_quad(pts)
        if ordinati is not None:
            candidato, miglior_score = ordinati, score

    if candidato is None:
        return None
    candidato = candidato + np.float32([x1, y1])
    angoli = np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])
    scarto = np.abs(candidato - angoli)
    if (scarto[:, 0] > 0.15 * bw).any() or (scarto[:, 1] > 0.20 * bh).any():
        return None
    if not cv2.isContourConvex(candidato.reshape(-1, 1, 2)):
        return None
    if cv2.contourArea(candidato.reshape(-1, 1, 2)) < 0.60 * area_box:
        return None
    return [(float(x), float(y)) for x, y in candidato]


# ------------------------------------------------------------------ tracker
class KeyboardTracker:
    """Segue la tastiera: detector periodico + tracker leggero fra una rilevazione e l'altra."""

    def __init__(self, detector: "PianoDetector", conf: float = 0.15,
                 tracker: str = "template", intervallo_redetect: int = 30,
                 soglia_somiglianza: float = 0.55, ema: float = 0.35,
                 raffina_quad: bool = True) -> None:
        if tracker not in ("template", "mil"):
            raise ValueError(f"tracker sconosciuto: {tracker!r} (usa 'template' o 'mil')")
        self.detector = detector
        self.conf = float(conf)
        self.tracker_tipo = tracker
        self.intervallo = max(1, int(intervallo_redetect))
        self.soglia = float(soglia_somiglianza)
        self.ema = float(min(max(ema, 0.0), 0.95))   # 0 = nessuno smoothing
        self.raffina_quad = bool(raffina_quad)
        self.reset()

    # ------------------------------------------------------------------ API
    def reset(self) -> None:
        """Dimentica lo stato: il prossimo init()/update() rilevera' da zero."""
        self._box = None          # box grezzo [x1,y1,x2,y2] (float), usato per il tracking
        self._box_out = None      # box smussato con EMA, quello restituito
        self._quad_rel = None     # vertici in coordinate relative al box (0-1)
        self._template = None     # patch in grigio a scala di lavoro
        self._mil = None
        self._ultimo_det = -10 ** 9
        self._ultimo_agg = -10 ** 9
        self._ultima_sim = 0.0
        self.ultima_classe = None  # classe del detector usata all'ultima adozione

    def init(self, frame: np.ndarray, frame_idx: int = 0) -> Traccia | None:
        """Rileva la tastiera con la rete neurale e inizializza il tracker."""
        self.reset()
        self._ultimo_det = frame_idx
        det = self._rileva(frame)
        if det is None:
            return None
        return self._adotta(frame, _grigio(frame), [det.x1, det.y1, det.x2, det.y2],
                            frame_idx, det.confidenza)

    def update(self, frame: np.ndarray, frame_idx: int) -> Traccia | None:
        """Aggiorna la traccia sul frame; None se la tastiera non si trova (mai box inventati)."""
        if self._box is None:
            if frame_idx - self._ultimo_det >= _RETRY_PERSO:
                return self.init(frame, frame_idx)
            return None

        gray = _grigio(frame)
        box_new, sim = self._segui(frame, gray)
        self._ultima_sim = sim
        ok = box_new is not None and sim >= self.soglia
        scaduto = (frame_idx - self._ultimo_det) >= self.intervallo
        riprova = (frame_idx - self._ultimo_det) >= _RETRY_PERSO

        if scaduto or (not ok and riprova):
            self._ultimo_det = frame_idx
            det = self._rileva(frame)
            if det is not None:
                box_det = [float(det.x1), float(det.y1), float(det.x2), float(det.y2)]
                if not ok:  # forzata: il tracker ha perso il bersaglio
                    return self._adotta(frame, gray, box_det, frame_idx, det.confidenza)
                iou = _iou(box_new, box_det)
                if iou >= 0.5:  # concordi: media, per correggere scala/deriva senza salti
                    misto = [0.5 * a + 0.5 * b for a, b in zip(box_new, box_det)]
                    return self._adotta(frame, gray, misto, frame_idx, det.confidenza,
                                        mantieni_out=True)
                if sim < self.soglia + 0.15:  # discordi e tracker incerto: ci si fida della rete
                    return self._adotta(frame, gray, box_det, frame_idx, det.confidenza)
                # discordi ma tracker solido: il box del detector e' un outlier, si ignora

        if not ok:
            return None   # perso e nessuna rilevazione: nessun box inventato

        self._box = box_new
        h, w = frame.shape[:2]
        self._box = _clamp_box(self._box, w, h)
        self._aggiorna_template(gray, sim, frame_idx)
        if self._box_out is None or self.ema <= 0:
            self._box_out = list(self._box)
        else:
            self._box_out = [self.ema * o + (1.0 - self.ema) * n
                             for o, n in zip(self._box_out, self._box)]
        return self._costruisci_traccia(frame_idx, "tracker", sim, (h, w))

    # ------------------------------------------------------------- interni
    def _rileva(self, frame: np.ndarray):
        """Migliore rilevazione per la GEOMETRIA dei tasti: 'musical keyboard' > 'piano'."""
        dets = [d for d in self.detector.detect_all(frame) if d.confidenza >= self.conf]
        if not dets:
            return None
        tastiere = [d for d in dets if d.classe == CLASSE_PREFERITA]
        scelta = tastiere[0] if tastiere else dets[0]   # liste gia' ordinate per confidenza
        self.ultima_classe = scelta.classe
        return scelta

    def _adotta(self, frame, gray, box, frame_idx, conf, mantieni_out: bool = False) -> Traccia | None:
        """Imposta box, template, quad e tracker MIL a partire da un box (float)."""
        h, w = frame.shape[:2]
        box = _clamp_box(box, w, h)
        s = _SCALA_LAVORO
        tx1, ty1 = int(round(box[0] * s)), int(round(box[1] * s))
        tx2, ty2 = int(round(box[2] * s)), int(round(box[3] * s))
        patch = gray[ty1:ty2, tx1:tx2]
        if patch.shape[0] < 8 or patch.shape[1] < 8:
            return None
        self._template = patch.copy()
        self._box = list(box)
        if self._box_out is None or not mantieni_out:
            self._box_out = list(box)
        else:
            self._box_out = [self.ema * o + (1.0 - self.ema) * n
                             for o, n in zip(self._box_out, box)]
        self._ultimo_agg = frame_idx

        quad = _raffina_quad(frame, box) if self.raffina_quad else None
        bw, bh = box[2] - box[0], box[3] - box[1]
        if quad is None:
            self._quad_rel = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        else:
            self._quad_rel = [((x - box[0]) / bw, (y - box[1]) / bh) for x, y in quad]

        if self.tracker_tipo == "mil":
            self._avvia_mil(frame, box)
        return self._costruisci_traccia(frame_idx, "detector", conf, (h, w),
                                        con_quad=quad is not None)

    def _avvia_mil(self, frame, box) -> None:
        try:
            self._mil = cv2.TrackerMIL_create()
            self._mil.init(frame, (int(box[0]), int(box[1]),
                                   int(box[2] - box[0]), int(box[3] - box[1])))
        except (AttributeError, cv2.error) as e:
            warnings.warn(f"TrackerMIL non disponibile ({e}): ripiego sul template matching.")
            self._mil = None
            self.tracker_tipo = "template"

    def _segui(self, frame, gray):
        """Un passo di tracking -> (box [x1,y1,x2,y2] | None, somiglianza 0-1)."""
        if self.tracker_tipo == "mil" and self._mil is not None:
            try:
                ok, bb = self._mil.update(frame)
            except cv2.error:
                return None, 0.0
            if not ok:
                return None, 0.0
            x, y, bw, bh = [float(v) for v in bb]
            box = [x, y, x + bw, y + bh]
            return box, self._somiglianza_in_box(gray, box)
        return self._segui_template(frame, gray)

    def _segui_template(self, frame, gray):
        s = _SCALA_LAVORO
        th, tw = self._template.shape[:2]
        H, W = frame.shape[:2]
        x1, y1, x2, y2 = self._box
        bw, bh = x2 - x1, y2 - y1
        r = max(40.0, 0.25 * bh)                       # raggio di ricerca (px frame)
        gx1 = int(math.floor(max(0.0, x1 - r) * s))
        gy1 = int(math.floor(max(0.0, y1 - r) * s))
        gx2 = int(math.ceil(min(float(W), x2 + r) * s))
        gy2 = int(math.ceil(min(float(H), y2 + r) * s))
        regione = gray[gy1:gy2, gx1:gx2]
        if regione.shape[0] < th or regione.shape[1] < tw:
            return None, 0.0
        res = cv2.matchTemplate(regione, self._template, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        if not np.isfinite(maxv):
            return None, 0.0
        nx1 = (gx1 + maxloc[0]) / s
        ny1 = (gy1 + maxloc[1]) / s
        return [nx1, ny1, nx1 + bw, ny1 + bh], float(max(0.0, min(1.0, maxv)))

    def _somiglianza_in_box(self, gray, box) -> float:
        """Somiglianza fra il template e il contenuto di `box` (usata col tracker MIL)."""
        s = _SCALA_LAVORO
        th, tw = self._template.shape[:2]
        x1, y1, x2, y2 = [int(round(v * s)) for v in box]
        x1, y1 = max(0, x1), max(0, y1)
        patch = gray[y1:y2, x1:x2]
        if patch.shape[0] < 8 or patch.shape[1] < 8:
            return 0.0
        patch = cv2.resize(patch, (tw, th), interpolation=cv2.INTER_AREA)
        v = float(cv2.matchTemplate(patch, self._template, cv2.TM_CCOEFF_NORMED)[0, 0])
        return float(max(0.0, min(1.0, v))) if np.isfinite(v) else 0.0

    def _aggiorna_template(self, gray, sim: float, frame_idx: int) -> None:
        """EMA del template: raro e solo con somiglianza alta, per non inseguire il drift."""
        if sim < _SOGLIA_AGG_TEMPLATE or frame_idx - self._ultimo_agg < _AGG_TEMPLATE_OGNI:
            return
        s = _SCALA_LAVORO
        th, tw = self._template.shape[:2]
        x1, y1 = int(round(self._box[0] * s)), int(round(self._box[1] * s))
        patch = gray[y1:y1 + th, x1:x1 + tw]
        if patch.shape != self._template.shape:
            return
        self._template = cv2.addWeighted(self._template, 1.0 - _ALFA_TEMPLATE,
                                         patch, _ALFA_TEMPLATE, 0.0)
        self._ultimo_agg = frame_idx

    def _costruisci_traccia(self, frame_idx, origine, conf, shape, con_quad: bool = True) -> Traccia:
        h, w = shape
        x1, y1, x2, y2 = _clamp_box(self._box_out, w, h)
        quad = None
        if self._quad_rel is not None and con_quad is not False and self._quad_e_reale():
            bw, bh = x2 - x1, y2 - y1
            quad = [(x1 + u * bw, y1 + v * bh) for u, v in self._quad_rel]
        return Traccia(int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)),
                       float(min(max(conf, 0.0), 1.0)), origine, int(frame_idx), quad)

    def _quad_e_reale(self) -> bool:
        """True se il quad relativo non e' il semplice rettangolo (altrimenti e' inutile)."""
        rett = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        return any(abs(a - c) > 1e-6 or abs(b - d) > 1e-6
                   for (a, b), (c, d) in zip(self._quad_rel, rett))

````

### `motore_calibrato.py`

````python
"""
Motore calibrato — decide premuto/rilasciato DENTRO le sagome per nota.

Fasi 4-5 di BRIEF_CLAUDE_2_SAGOME.md. Sottoprocesso lanciato dal server:

    python3 motore_calibrato.py video.mp4 -o out/ [--quad "x,y x,y x,y x,y"]
        [--prima-nota N] [--cartella-sagome DIR] [--formato-clip mp4|jpeg]

COSA SIGNIFICA "PREMUTO" (misurato, non indovinato)
---------------------------------------------------
Per ogni nota e frame si prende il patch grigio (6x10) della zona del tasto:
  * bianco: fascia frontale, sotto i neri, centrata (meno 20% per lato);
  * nero: nucleo centrale (meno 25% per lato, 10% in alto/basso).
RIPOSO = mediana temporale del patch su TUTTO il video: un tasto sta a riposo la
maggior parte del tempo, quindi la mediana e' l'immagine di riposo anche se all'inizio
e' gia' premuto (basta che non lo sia per piu' di meta' del video).
d(t) = differenza media assoluta dal riposo (livelli di grigio).
Contrasto LOCALE: l(t) = d(t) - mediana di d(t) sui tasti vicini dello stesso colore
(+-3): una mano che copre molti tasti alza tutti i vicini e viene soppressa; un dito su
un tasto alza solo quello.
score = clip(l / 25, 0, 1); mediana su `finestra` frame; isteresi soglia_giu / soglia_su.
Un tasto tenuto = UNA nota (on all'inizio, off alla fine). Sotto 2 frame: scartata.
Note non in `visibili`: non esistono qui, quindi non possono essere emesse.

LIMITE DICHIARATO: da una camera 2D un dito che sfiora il tasto senza premere cambia
l'immagine come un dito che preme. Le soglie vanno tarate sul video reale.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from note_events import EventoNota
from sagome import (SagomeVideo, regione_tastiera, riquadri_per_frame, salva_sagome,
                    scrivi_clip_per_nota)
from to_midi import riepiloga, salva_json, salva_midi

_PATCH = (6, 10)            # (larghezza, altezza) del patch di analisi
_SCALA_L = 25.0             # livelli di grigio di contrasto locale = score 1
_VICINI = 3


class RilevatoreCalibrato:
    """Decide premuto/rilasciato per nota, dentro i riquadri di `sagome`."""

    def __init__(self, sagome: SagomeVideo, *, soglia_giu: float = 0.6,
                 soglia_su: float = 0.4, finestra: int = 5) -> None:
        if not 0.0 < soglia_su < soglia_giu <= 1.0:
            raise ValueError("servono 0 < soglia_su < soglia_giu <= 1 (isteresi)")
        if finestra < 1 or finestra % 2 == 0:
            raise ValueError("finestra deve essere un intero dispari >= 1")
        self.sagome = sagome
        self.soglia_giu, self.soglia_su, self.finestra = float(soglia_giu), float(soglia_su), int(finestra)
        self._emesse: list[int] = []
        self._eventi: list[EventoNota] = []

    # ------------------------------------------------------------------ API
    def note_emesse(self) -> list[int]:
        """Note per cui e' uscito almeno un evento (sempre sottoinsieme di sagome.visibili)."""
        return sorted(set(self._emesse))

    def analizza(self, video, out_dir, *, max_secondi: float | None = None,
                 sagome_dir=None, formato_clip: str = "mp4", scrivi_clip: bool = True) -> dict:
        """Scrive notes.json, song.mid, prima_griglia.jpg (+ sagome.json e sagome/ in `sagome_dir`)."""
        s = self.sagome
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        sag = Path(sagome_dir) if sagome_dir else out
        score = self._score(video, max_secondi)
        self._eventi = self._eventi_da_score(score)
        self._emesse = [e.nota for e in self._eventi]
        fuori = set(self._emesse) - set(s.visibili)
        if fuori:                                           # non deve mai accadere: lo si verifica
            raise AssertionError(f"note emesse fuori da `visibili`: {sorted(fuori)}")

        durata = s.n_frame / s.fps
        vis = s.visibili
        ext = {"prima_nota": min(vis), "ultima_nota": max(vis), "n_tasti": len(vis)}
        meta = {"video": s.video, "fps": s.fps, "frame_totali": s.n_frame, "durata_s": durata,
                "larghezza": 0, "altezza": 0, "estensione_tastiera": ext}
        cap = cv2.VideoCapture(str(video))
        meta["larghezza"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        meta["altezza"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        ok, primo = cap.read()
        cap.release()
        if ok:
            cv2.imwrite(str(out / "prima_griglia.jpg"), self._disegna(primo))
        salva_json(self._eventi, str(out / "notes.json"), meta)
        doc = json.loads((out / "notes.json").read_text(encoding="utf-8"))
        doc["motore"] = "calibrato"
        doc["calibrato"] = {"visibili": vis, "emesse": self.note_emesse(), "ottava": s.ottava,
                            "soglie": {"giu": self.soglia_giu, "su": self.soglia_su,
                                       "finestra": self.finestra}}
        (out / "notes.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False),
                                        encoding="utf-8")
        salva_midi(self._eventi, str(out / "song.mid"))
        salva_sagome(s, sag / "sagome.json")
        clip: list[Path] = []
        if scrivi_clip:
            clip = scrivi_clip_per_nota(s, video, sag / "sagome", formato=formato_clip)
        r = riepiloga(self._eventi, durata)
        return {"n_frame": s.n_frame, "visibili": vis, "emesse": self.note_emesse(),
                "n_eventi": r["n_eventi"], "riepilogo": r, "n_clip": len(clip),
                "ottava": {k: s.ottava[k] for k in ("scelta", "ambigua", "ipotesi_usata")}}

    # -------------------------------------------------------------- interni
    def _zona(self, r) -> tuple[int, int, int, int]:
        """Sotto-rettangolo di analisi dentro il riquadro (vedi docstring del modulo)."""
        g = self.sagome.ottava["prova"]["geometria_canonica"]
        ya, yb = g["banda_neri"]
        W, H = r.x2 - r.x1, r.y2 - r.y1
        if r.nero:
            return (int(r.x1 + 0.25 * W), int(r.y1 + 0.10 * H),
                    int(r.x2 - 0.25 * W), int(r.y2 - 0.10 * H))
        frac = (yb - ya) / max(1.0, g["hc"] - 1 - ya) + 0.10
        return (int(r.x1 + 0.20 * W), int(r.y1 + min(frac, 0.9) * H),
                int(r.x2 - 0.20 * W), int(r.y2 - 0.05 * H))

    def _score(self, video, max_secondi) -> np.ndarray:
        s = self.sagome
        note = s.visibili
        patch = np.zeros((len(note), s.n_frame, _PATCH[0] * _PATCH[1]), np.uint8)
        cap = cv2.VideoCapture(str(video))
        for i in range(s.n_frame):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"il video ha meno frame di quelli attesi ({i} < {s.n_frame})")
            gr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h, w = gr.shape
            for k, n in enumerate(note):
                x1, y1, x2, y2 = self._zona(s.riquadri[n][i])
                x1, x2 = max(0, x1), min(w, x2)
                y1, y2 = max(0, y1), min(h, y2)
                if x2 - x1 >= 1 and y2 - y1 >= 1:
                    patch[k, i] = cv2.resize(gr[y1:y2, x1:x2], _PATCH,
                                             interpolation=cv2.INTER_AREA).ravel()
        cap.release()
        rif = np.median(patch, axis=1, keepdims=True)                 # riposo = mediana temporale
        d = np.abs(patch.astype(np.float32) - rif).mean(axis=2)       # (n_note, n_frame)
        neri = np.array([s.riquadri[n][0].nero for n in note])
        loc = np.zeros_like(d)
        for k in range(len(note)):
            stessi = np.where(neri == neri[k])[0]
            pos = int(np.where(stessi == k)[0][0])
            vic = [stessi[j] for j in range(max(0, pos - _VICINI), min(len(stessi), pos + _VICINI + 1))
                   if j != pos]
            loc[k] = d[k] - (np.median(d[vic], axis=0) if vic else 0.0)
        sc = np.clip(loc / _SCALA_L, 0.0, 1.0)
        return self._mediana_tempo(sc)

    def _mediana_tempo(self, sc: np.ndarray) -> np.ndarray:
        if self.finestra == 1:
            return sc
        r = self.finestra // 2
        pad = np.pad(sc, ((0, 0), (r, r)), mode="edge")
        return np.median(np.stack([pad[:, j:j + sc.shape[1]] for j in range(2 * r + 1)]), axis=0)

    def _eventi_da_score(self, sc: np.ndarray) -> list[EventoNota]:
        s = self.sagome
        eventi: list[EventoNota] = []
        for k, n in enumerate(s.visibili):
            on, i_on, picco = False, 0, 0.0
            rs = s.riquadri[n]
            for i in range(s.n_frame):
                if not rs[i].visibile:                       # assenza: si chiude all'ultimo frame buono
                    if on:
                        eventi += self._chiudi(n, i_on, i - 1, picco)
                        on = False
                    continue
                v = float(sc[k, i])
                if not on and v >= self.soglia_giu:
                    on, i_on, picco = True, i, v
                elif on:
                    picco = max(picco, v)
                    if v < self.soglia_su:
                        eventi += self._chiudi(n, i_on, i, picco)
                        on = False
            if on:
                eventi += self._chiudi(n, i_on, s.n_frame - 1, picco)
        eventi.sort(key=lambda e: (e.onset, e.nota))
        return eventi

    def _chiudi(self, nota: int, i_on: int, i_off: int, picco: float) -> list[EventoNota]:
        s = self.sagome
        if i_off - i_on < 2:                                 # sotto 2 frame: rumore
            return []
        vel = int(min(max(round(40 + 87 * picco), 1), 127))
        return [EventoNota(nota=nota, onset=i_on / s.fps, offset=i_off / s.fps, velocity=vel,
                           profondita=round(float(picco), 3), mano="", frame_onset=i_on,
                           frame_offset=i_off)]

    def _disegna(self, frame: np.ndarray) -> np.ndarray:
        img = frame.copy()
        s = self.sagome
        q = np.int32(s.quad[0]).reshape(-1, 1, 2)
        cv2.polylines(img, [q], True, (0, 235, 0), 2, cv2.LINE_AA)
        for n in sorted(s.visibili, key=lambda m: s.riquadri[m][0].nero):    # i neri sopra
            r = s.riquadri[n][0]
            col = (60, 60, 255) if r.nero else (255, 160, 30)
            cv2.rectangle(img, (r.x1, r.y1), (r.x2, r.y2), col, 1, cv2.LINE_AA)
            if n % 12 == 0:                                                 # etichetta ogni Do
                cv2.rectangle(img, (r.x1, r.y1), (r.x2, r.y2), (0, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(img, r.nome, (r.x1, max(12, r.y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(img, r.nome, (r.x1, max(12, r.y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 255, 255), 1, cv2.LINE_AA)
        o = s.ottava
        txt = ("ottava: %s" % o["scelta"]) if not o["ambigua"] else \
              ("OTTAVA AMBIGUA - ipotesi %s (%d candidate)" % (o["ipotesi_usata"], len(o["candidate"])))
        cv2.putText(img, f"calibrato: {len(s.visibili)} note inquadrate; {txt}", (12, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, f"calibrato: {len(s.visibili)} note inquadrate; {txt}", (12, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 235, 0), 1, cv2.LINE_AA)
        return img


# ---------------------------------------------------------------------- CLI
def _quad_da_testo(t: str):
    num = [float(x) for x in t.replace(";", " ").replace(",", " ").split()]
    if len(num) != 8:
        raise ValueError("--quad vuole 8 numeri: x,y dei 4 angoli")
    return [(num[0], num[1]), (num[2], num[3]), (num[4], num[5]), (num[6], num[7])]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Motore calibrato: sagome per nota -> MIDI.")
    p.add_argument("video")
    p.add_argument("-o", "--output", default="out")
    p.add_argument("--quad", default=None, help='4 angoli TL TR BR BL: "x,y x,y x,y x,y"')
    p.add_argument("--prima-nota", type=int, default=None)
    p.add_argument("--nota-min", type=int, default=21)
    p.add_argument("--nota-max", type=int, default=108)
    p.add_argument("--max-secondi", type=float, default=None)
    p.add_argument("--soglia-giu", type=float, default=0.6)
    p.add_argument("--soglia-su", type=float, default=0.4)
    p.add_argument("--finestra", type=int, default=5)
    p.add_argument("--cartella-sagome", default=None, help="dove scrivere sagome.json e sagome/")
    p.add_argument("--formato-clip", choices=("mp4", "jpeg"), default="mp4")
    p.add_argument("--senza-clip", action="store_true")
    a = p.parse_args(argv)
    t0 = time.time()
    try:
        cap = cv2.VideoCapture(a.video)
        if not cap.isOpened():
            print(f"[ERRORE] impossibile aprire il video: {a.video}", file=sys.stderr)
            return 2
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        print(f"[video] {a.video}: {W}x{H}, {fps:.3f} fps, {n} frame, passo=1")
        quad = _quad_da_testo(a.quad) if a.quad else None
        print("[calibrato] fase 1: regione della tastiera", "(4 angoli dati)" if quad else "(YOLO + tracker)")
        regione = regione_tastiera(a.video, quad=quad, max_secondi=a.max_secondi)
        print("[calibrato] fase 2: riquadri per nota e per frame")
        s = riquadri_per_frame(a.video, regione, nota_min=a.nota_min, nota_max=a.nota_max,
                               prima_nota=a.prima_nota, max_secondi=a.max_secondi)
        v = s.visibili
        print(f"[griglia] estensione {min(v)}..{max(v)} ({len(v)} note inquadrate) - "
              f"{'ottava AMBIGUA, ipotesi ' + str(s.ottava['ipotesi_usata']) if s.ottava['ambigua'] else 'ottava ' + str(s.ottava['scelta'])}")
        print("[calibrato] fasi 3-5: decisione, clip, uscita")
        r = RilevatoreCalibrato(s, soglia_giu=a.soglia_giu, soglia_su=a.soglia_su,
                                finestra=a.finestra).analizza(
            a.video, a.output, max_secondi=a.max_secondi, sagome_dir=a.cartella_sagome,
            formato_clip=a.formato_clip, scrivi_clip=not a.senza_clip)
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"[ERRORE] {e}", file=sys.stderr)
        return 2
    print("\n=== RIEPILOGO ===")
    print(f"frame                 : {r['n_frame']}")
    print(f"note inquadrate       : {len(r['visibili'])}  emesse {len(r['emesse'])}")
    print(f"eventi nota           : {r['n_eventi']} (note uniche {r['riepilogo']['note_uniche']})")
    print(f"clip scritte          : {r['n_clip']}")
    print(f"tempo                 : {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

````

### `sagome.py`

````python
"""
Sagome — "dove guardare", per nota e per frame, misurato sul singolo video.

Motore "calibrato", fase 1-3 (BRIEF_CLAUDE_2_SAGOME.md).

Una SAGOMA e' un rettangolo: l'area del frame dove si decide se *quella* nota e'
premuta *in quel* frame. Nessun modello da addestrare: geometria misurata.

COME SI MISURA
--------------
1. regione_tastiera(): quadrilatero della tastiera per frame (YOLO + tracker gia'
   in keyboard_tracker.py, oppure i 4 angoli dati a mano).
2. riquadri_per_frame(): ogni frame viene raddrizzato (omografia) in una striscia
   canonica. Sulla striscia, con la MEDIANA di molti frame (le mani si muovono, i
   tasti no), si misura:
     * la banda dei tasti neri (righe con piu' alternanza scuro/chiaro);
     * i centri dei neri -> larghezza del tasto bianco `w` (spaziature w / 2w);
     * l'estensione reale della tastiera (colonne "tasto" chiare nella fascia frontale);
     * la FASE dei neri (schema 2-3 = spaziature 1,2,1,1,2) -> quale nota e' ogni tasto.
   Poi per OGNI frame un piccolo scarto orizzontale (correlazione del profilo dei
   neri col modello, entro +-0.3 w) corregge la deriva: un frame con confidenza
   bassa riusa l'ultimo scarto buono (e abbassa la confidenza); non inventa nulla.
3. Un tasto e' `visibile` solo se sta per intero dentro la tastiera misurata.
   Le note non inquadrate non hanno riquadri e non compaiono in `visibili`.

OTTAVA (D3): lo schema dei neri dice la nota entro l'ottava (fase), NON l'ottava.
Si calcolano tutte le posizioni compatibili con 21..108 (e con nota_min/nota_max).
Se resta una sola -> `scelta`. Se restano piu' candidate -> `scelta` = None, si
elencano le candidate e si dichiara l'ipotesi usata (`ipotesi_usata`, `ambigua`).
La fase e' verificata su 4 segmenti del video (`segmenti_concordi`).

ASSUNZIONI (da verificare sul video reale):
  * il quadrilatero arriva fino al bordo frontale dei tasti (v=1);
  * le mani non coprono gli stessi tasti per tutto il video (mediana temporale);
  * tasti neri piu' scuri dei bianchi.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from keyboard_grid import MIDI_MAX, MIDI_MIN, _OFFSET_NERI, e_nero, nome_nota

QUI = Path(__file__).resolve().parent
_SCHEMA_NERI = (1, 2, 1, 1, 2)          # spaziature (in bianchi) C#-D#, D#-F#, F#-G#, G#-A#, A#-C#
_PC_NERI = (1, 3, 6, 8, 10)
_N_STIMA = 60                           # frame campionati per la stima globale
_SOGLIA_NCC = 0.35                      # sotto: il frame non corregge lo scarto (confidenza bassa)
_BIANCHI_88 = [n for n in range(MIDI_MIN, MIDI_MAX + 1) if not e_nero(n)]


# ------------------------------------------------------------------ dati
@dataclass(slots=True)
class RiquadroNota:
    nota: int
    nome: str
    nero: bool
    frame: int
    t: float
    x1: int
    y1: int
    x2: int
    y2: int
    visibile: bool
    confidenza: float


@dataclass
class SagomeVideo:
    video: str
    fps: float
    n_frame: int
    quad: list
    riquadri: dict
    visibili: list
    ottava: dict
    H_serie: list | None = None      # omografia per frame (solo motore prospettico): serve a
                                     # ridisegnare il video con i tasti premuti in evidenza.
                                     # Non viene salvata in sagome.json: chi la riusa non ce l'ha.


# ------------------------------------------------------------- utilita'
def _apri(video):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"impossibile aprire il video: {video}")
    return cap


def _fps(cap) -> float:
    f = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    return f if math.isfinite(f) and f > 0 else 30.0


def _lati(q: np.ndarray) -> tuple[float, float]:
    lw = 0.5 * (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3]))
    lh = 0.5 * (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1]))
    return float(lw), float(lh)


def _dim_canonica(q: np.ndarray) -> tuple[int, int]:
    lw, lh = _lati(q)
    wc = int(min(max(round(lw), 400), 2400))
    hc = int(min(max(round(wc * lh / max(lw, 1.0)), 60), 900))
    return wc, hc


def _omografia(q: np.ndarray, wc: int, hc: int) -> np.ndarray:
    dst = np.float32([[0, 0], [wc, 0], [wc, hc], [0, hc]])
    return cv2.getPerspectiveTransform(np.float32(q).reshape(4, 2), dst)


def _grigio_canonico(frame, q, wc, hc) -> np.ndarray:
    M = _omografia(q, wc, hc)
    return cv2.cvtColor(cv2.warpPerspective(frame, M, (wc, hc)), cv2.COLOR_BGR2GRAY)


# ---------------------------------------------------------- 1. regione
def regione_tastiera(video, *, quad=None, ogni_frame: bool = True,
                     max_secondi: float | None = None) -> list:
    """
    Quadrilatero (TL, TR, BR, BL) della tastiera per ogni frame.

    quad: se dato (4 punti in pixel del frame) vale per tutti i frame. Altrimenti
    YOLO (`musical keyboard`, ripiego `piano`) + KeyboardTracker. Se `ogni_frame`
    e' False il tracker gira 1 frame su 5 e fra uno e l'altro si tiene l'ultimo quad.
    Serve `weights/yolov8l-oiv7.pt` (nessun download): se manca, errore chiaro.
    """
    cap = _apri(video)
    fps = _fps(cap)
    limite = int(max_secondi * fps) if max_secondi else None
    quad_fisso = None
    if quad is not None:
        quad_fisso = np.float32(quad).reshape(4, 2)
    tracker = None
    if quad_fisso is None:
        pesi = next((p for p in (Path("weights/yolov8l-oiv7.pt"), QUI / "weights/yolov8l-oiv7.pt",
                                 Path("weights/yolov8m-oiv7.pt"), QUI / "weights/yolov8m-oiv7.pt")
                     if p.is_file()), None)
        if pesi is None:
            cap.release()
            raise FileNotFoundError("pesi YOLO non trovati: attesi weights/yolov8l-oiv7.pt "
                                    "(o yolov8m). Nessun download automatico: oppure passa i 4 angoli.")
        from piano_detector import PianoDetector
        from keyboard_tracker import KeyboardTracker
        tracker = KeyboardTracker(PianoDetector(str(pesi), conf=0.15))
    risultato: list = []
    ultimo = None
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok or (limite is not None and i >= limite):
            break
        if quad_fisso is not None:
            q = quad_fisso
        else:
            if ogni_frame or i % 5 == 0 or ultimo is None:
                t = tracker.init(frame, i) if i == 0 else tracker.update(frame, i)
                if t is not None:
                    q = (np.float32(t.quad).reshape(4, 2) if t.quad is not None and len(t.quad) == 4
                         else np.float32([[t.x1, t.y1], [t.x2, t.y1], [t.x2, t.y2], [t.x1, t.y2]]))
                    ultimo = q
            q = ultimo
            if q is None:
                i += 1
                risultato.append(None)
                continue
        risultato.append([(float(x), float(y)) for x, y in q])
        i += 1
    cap.release()
    primo = next((q for q in risultato if q is not None), None)
    if primo is None:
        raise RuntimeError("tastiera mai rilevata: abbassa la confidenza o segna i 4 angoli")
    return [q if q is not None else primo for q in risultato]   # prima del 1o rilevamento: il 1o quad


# ------------------------------------------------- 2. misure sulla striscia
def _banda_neri(med: np.ndarray) -> tuple[int, int]:
    """Righe [ya, yb] con piu' alternanza scuro/chiaro (la banda dei neri)."""
    sd = med.std(axis=1)
    sd = np.convolve(sd, np.ones(5) / 5, mode="same")
    ok = sd > 0.5 * sd.max()
    best, cur, start = (0, 0), 0, 0
    for y, v in enumerate(ok):
        if v:
            if cur == 0:
                start = y
            cur += 1
            if cur > best[1] - best[0]:
                best = (start, start + cur)
        else:
            cur = 0
    ya, yb = best
    if yb - ya < 6:
        raise RuntimeError("banda dei tasti neri non trovata (tastiera non inquadrata bene?)")
    return int(ya), int(yb)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    out, s = [], None
    for x, v in enumerate(mask):
        if v and s is None:
            s = x
        elif not v and s is not None:
            out.append((s, x))
            s = None
    if s is not None:
        out.append((s, len(mask)))
    return out


def _misura_striscia(med: np.ndarray) -> dict:
    """Misure geometriche sulla striscia mediana: banda, neri, w, estensione tastiera."""
    hc, wc = med.shape
    ya, yb = _banda_neri(med)
    r0, r1 = ya + int(0.15 * (yb - ya)), yb - int(0.15 * (yb - ya))
    prof = med[r0:max(r1, r0 + 1)].mean(axis=0)
    prof_s = np.convolve(prof, np.ones(3) / 3, mode="same")
    soglia, _ = cv2.threshold(np.uint8(np.clip(prof_s, 0, 255)).reshape(1, -1), 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    scuro = prof_s < soglia
    runs = _runs(scuro)
    larg0 = float(np.median([b - a for a, b in runs])) if runs else 0.0
    # estensione: fascia frontale (sotto i neri), colonne chiare; chiusura dei separatori sottili
    f0 = min(hc - 2, yb + int(0.1 * (hc - yb)))
    fr = med[f0:hc].mean(axis=0)
    chiaro = (fr > 0.5 * (fr.max() + fr.min())).astype(np.uint8).reshape(1, -1)
    k = max(3, int(0.5 * larg0))
    chiaro = cv2.morphologyEx(chiaro, cv2.MORPH_CLOSE, np.ones((1, k), np.uint8)).ravel() > 0
    rr = _runs(chiaro)
    if not rr:
        raise RuntimeError("fascia frontale dei tasti non riconoscibile")
    xa, xb = max(rr, key=lambda r: r[1] - r[0])
    # i neri stanno DENTRO la tastiera: fuori dall'estensione sono margini scuri, non tasti
    runs = [(a, b) for a, b in runs if a >= xa and b <= xb]
    if len(runs) < 2:
        raise RuntimeError("meno di 2 tasti neri riconoscibili: impossibile misurare i tasti")
    med_l = float(np.median([b - a for a, b in runs]))
    neri = [(a, b) for a, b in runs if 0.5 * med_l <= (b - a) <= 1.6 * med_l]   # via artefatti
    centri = np.array([(a + b) / 2.0 for a, b in neri])
    sp = np.diff(centri)
    if len(sp) == 0:
        raise RuntimeError("tasti neri insufficienti per stimare la larghezza dei bianchi")
    w0 = float(np.median(sp[sp < 1.5 * sp.min()]))          # spaziatura "corta" (~1.1-1.2 w)
    g = np.where(sp / w0 >= 1.4, 2, 1).astype(int)           # 1 = vicini, 2 = c'e' un buco di un bianco
    # w dal modello reale: le spaziature attese non sono esattamente 1 e 2 (i neri sono
    # spostati di _OFFSET_NERI), quindi si usa la somma attesa per la fase compatibile
    attese = [1 + _OFFSET_NERI[3] - _OFFSET_NERI[1], 2 + _OFFSET_NERI[6] - _OFFSET_NERI[3],
              1 + _OFFSET_NERI[8] - _OFFSET_NERI[6], 1 + _OFFSET_NERI[10] - _OFFSET_NERI[8],
              2 + _OFFSET_NERI[1] - _OFFSET_NERI[10]]
    fasi = _fasi_compatibili(g.tolist())
    if fasi:
        w = float(np.mean([sp.sum() / sum(attese[(r + j) % 5] for j in range(len(sp))) for r in fasi]))
    else:
        w = float(sp.sum() / g.sum())
    return {"ya": ya, "yb": yb, "w": w, "centri": centri.tolist(), "gap": g.tolist(),
            "larg_nero": med_l, "span": (int(xa), int(xb)), "wc": wc, "hc": hc}


def _fasi_compatibili(gap: list[int]) -> list[int]:
    """Rotazioni r (classe del 1o nero 0..4) per cui la sequenza di spaziature e' coerente."""
    return [r for r in range(5)
            if all(gap[j] == _SCHEMA_NERI[(r + j) % 5] for j in range(len(gap)))]


def _griglia(m: dict, classe0: int, salto_ottava: int) -> dict:
    """
    Posizioni dei tasti sulla striscia, date la classe del 1o nero e l'ottava.
    Ritorna {nota: (xl, xr, nero, centro)} per i tasti INTERI dentro la tastiera.
    """
    w, c0 = m["w"], m["centri"][0]
    xa, xb = m["span"]
    pc0 = _PC_NERI[classe0]
    off = _OFFSET_NERI[pc0]
    confine = c0 - off * w                      # confine fra il bianco N-1 e il bianco N+1
    # nota del 1o nero: pc0 nell'ottava indicata (salto_ottava = numero MIDI del nero)
    n0 = salto_ottava
    iw = _BIANCHI_88.index(n0 - 1)              # indice del bianco a sinistra del confine
    tol = 0.15 * w
    k_min = int(math.floor((xa - confine) / w)) - 1
    k_max = int(math.ceil((xb - confine) / w)) + 1
    out: dict[int, tuple] = {}
    for j in range(k_min, k_max):               # bianco con bordo sinistro = confine + (j) w, j=0 e' N+1
        idx = iw + 1 + j
        xl = confine + j * w
        xr = xl + w
        if xl >= xa - tol and xr <= xb + tol:
            if not 0 <= idx < len(_BIANCHI_88):      # un tasto inquadrato non esiste sul pianoforte
                raise ValueError("griglia fuori da A0..C8: ottava incompatibile")
            out[_BIANCHI_88[idx]] = (xl, xr, False, (xl + xr) / 2)
    # i neri: fra due bianchi adiacenti (N-1, N+1)
    for n, (xl, xr, _, _) in list(out.items()):
        nn = n + 1
        if nn <= MIDI_MAX and e_nero(nn) and (n + 2) in out:
            conf = xr
            c = conf + _OFFSET_NERI[nn % 12] * w
            hw = m["larg_nero"] / 2.0
            out[nn] = (c - hw, c + hw, True, c)
    return out


def _candidate(m: dict, fasi: list[int], nota_min: int, nota_max: int) -> list[dict]:
    """Tutte le (fase, ottava) compatibili con 21..108 e con la finestra [nota_min, nota_max]."""
    cand = []
    for r in fasi:
        pc = _PC_NERI[r]
        for n0 in range(MIDI_MIN + 1, MIDI_MAX):
            if n0 % 12 != pc or not e_nero(n0) or (n0 - 1) not in _BIANCHI_88:
                continue
            try:
                gr = _griglia(m, r, n0)
            except ValueError:
                continue
            if not gr:
                continue
            note = sorted(gr)
            if note[0] < max(nota_min, MIDI_MIN) or note[-1] > min(nota_max, MIDI_MAX):
                continue
            # lo schema deve coincidere con i neri misurati (anche se i neri ai bordi sono tagliati)
            cand.append({"prima_nota": note[0], "ultima_nota": note[-1], "fase_pc": pc,
                         "nero_di_riferimento": n0})
    cand.sort(key=lambda c: (c["prima_nota"], c["fase_pc"]))
    return cand


def _profilo_neri(g: np.ndarray, ya: int, yb: int) -> np.ndarray:
    r0, r1 = ya + int(0.15 * (yb - ya)), max(yb - int(0.15 * (yb - ya)), ya + 2)
    return g[r0:r1].mean(axis=0).astype(np.float32)


def _scarto_frame(prof: np.ndarray, modello: np.ndarray, max_s: int) -> tuple[int, float]:
    """Scarto s (px) che massimizza la correlazione normalizzata col modello dei neri."""
    migliore, ncc_m = 0, -1.0
    p = prof - prof.mean()
    np_ = float(np.linalg.norm(p)) + 1e-6
    for s in range(-max_s, max_s + 1):
        m = np.roll(modello, s)
        m = m - m.mean()
        c = float(-(p @ m) / (np_ * (float(np.linalg.norm(m)) + 1e-6)))   # neri = scuro
        if c > ncc_m:
            migliore, ncc_m = s, c
    return migliore, ncc_m


# ------------------------------------------------------ 2b. cuore: riquadri
def riquadri_per_frame(video, quad, *, nota_min: int = 21, nota_max: int = 108,
                       prima_nota: int | None = None,
                       max_secondi: float | None = None) -> SagomeVideo:
    """
    Riquadri per nota e per frame (proiezione della griglia + raffinamento sull'immagine).

    quad: lista di quad (uno per frame, da regione_tastiera) oppure un solo quad.
    nota_min/nota_max: finestra entro cui l'ottava puo' cadere (restringe le candidate).
    prima_nota: (opzionale) prima nota visibile, indicata dall'utente: risolve l'ambiguita'.
    Il raffinamento fallito su un frame NON crea riquadri nuovi: riusa l'ultimo scarto
    buono con confidenza ridotta. Frame con confidenza < soglia vengono marcati nel campo
    `confidenza` e il motore non li usa per decidere.
    """
    cap = _apri(video)
    fps = _fps(cap)
    limite = int(max_secondi * fps) if max_secondi else None
    quad_lista = quad if (len(quad) and isinstance(quad[0][0], (tuple, list))) else None
    q_unico = None if quad_lista is not None else np.float32(quad).reshape(4, 2)

    def q_del(i):
        if q_unico is not None:
            return q_unico
        return np.float32(quad_lista[min(i, len(quad_lista) - 1)]).reshape(4, 2)

    # --- passo A: frame campione per la stima globale (mediana)
    n_tot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if limite is not None and n_tot:
        n_tot = min(n_tot, limite)
    if n_tot <= 0:                                   # conteggio non affidabile: lo si misura
        c2 = _apri(video)
        n_tot = 0
        while c2.grab() and (limite is None or n_tot < limite):
            n_tot += 1
        c2.release()
    passo = max(1, n_tot // _N_STIMA)
    wc, hc = _dim_canonica(q_del(0))
    campioni: list[np.ndarray] = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok or i >= n_tot:
            break
        if i % passo == 0:
            campioni.append(_grigio_canonico(frame, q_del(i), wc, hc))
        i += 1
    cap.release()
    if not campioni:
        raise RuntimeError("video vuoto o illeggibile")
    pila = np.stack(campioni).astype(np.float32)
    med = np.median(pila, axis=0)
    m = _misura_striscia(med)
    # fase per segmenti del video (4): servono a dichiarare quanto e' stabile
    seg = np.array_split(np.arange(len(campioni)), min(4, len(campioni)))
    fasi_seg = []
    for idx in seg:
        try:
            ms = _misura_striscia(np.median(pila[idx], axis=0))
            fasi_seg.append(sorted(_fasi_compatibili(ms["gap"])))
        except RuntimeError:
            fasi_seg.append(None)
    fasi = _fasi_compatibili(m["gap"])
    if not fasi:
        raise RuntimeError("lo schema dei tasti neri misurato non e' coerente con un pianoforte "
                           f"(spaziature {m['gap']}): controlla i 4 angoli")
    cand = _candidate(m, fasi, nota_min, nota_max)
    if not cand:
        raise RuntimeError("nessuna ottava compatibile con la finestra richiesta "
                           f"({nota_min}..{nota_max}); fasi {fasi}")

    # --- scelta/dichiarazione dell'ottava
    scelta, usata, motivo = None, None, ""
    if prima_nota is not None:
        ok_u = [c for c in cand if c["prima_nota"] == int(prima_nota)]
        if not ok_u:
            raise RuntimeError(f"prima_nota={prima_nota} non e' fra le candidate: "
                               f"{[c['prima_nota'] for c in cand]}")
        scelta, usata, motivo = ok_u[0]["prima_nota"], ok_u[0], "indicata dall'utente"
    elif len(cand) == 1:
        scelta, usata = cand[0]["prima_nota"], cand[0]
        motivo = "unica posizione compatibile con 21..108 e con lo schema dei neri"
    else:
        usata = min(cand, key=lambda c: abs((c["prima_nota"] + c["ultima_nota"]) / 2 - 64.5))
        motivo = (f"{len(cand)} posizioni compatibili: lo schema dei neri fissa la nota entro "
                  "l'ottava, non l'ottava. Ipotesi usata = la piu' vicina al centro del pianoforte")
    gr = _griglia(m, [r for r in range(5) if _PC_NERI[r] == usata["fase_pc"]][0],
                  usata["nero_di_riferimento"])
    note_vis = sorted(gr)
    ottava = {
        "scelta": scelta, "ambigua": scelta is None,
        "ipotesi_usata": None if scelta is not None else usata["prima_nota"],
        "candidate": cand,
        "prova": {
            "motivo": motivo,
            "n_bianchi_misurati": round((m["span"][1] - m["span"][0]) / m["w"], 2),
            "n_neri_osservati": len(m["centri"]),
            "spaziature_neri": m["gap"],
            "fasi_compatibili_pc": [_PC_NERI[r] for r in fasi],
            "fasi_per_segmento": [None if f is None else [_PC_NERI[r] for r in f] for f in fasi_seg],
            "segmenti_concordi": all(f == sorted(fasi) for f in fasi_seg if f is not None),
            "larghezza_bianco_px": round(m["w"], 2),
            "frame_campione": len(campioni),
            "nota": ("tastiera intera in campo: ottava univoca" if len(cand) == 1 and
                     len(note_vis) >= 80 else None),
        },
    }

    # --- modello del profilo dei neri (binario) per la correzione per frame
    modello = np.full(wc, 255.0, np.float32)
    for n, (xl, xr, nero, c) in gr.items():
        if nero:
            modello[max(0, int(xl)):min(wc, int(math.ceil(xr)))] = 0.0
    max_s = max(2, int(0.3 * m["w"]))
    ya, yb = m["ya"], m["yb"]

    # --- passo B: ogni frame
    cap = _apri(video)
    riq: dict[int, list] = {n: [] for n in note_vis}
    quad_out = []
    s_prec, conf_prec = 0, 0.0
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok or i >= n_tot:
            break
        q = q_del(i)
        quad_out.append([(float(x), float(y)) for x, y in q])
        g = _grigio_canonico(frame, q, wc, hc)
        s, ncc = _scarto_frame(_profilo_neri(g, ya, yb), modello, max_s)
        if ncc >= _SOGLIA_NCC:
            s_prec, conf = s, float(min(1.0, max(0.0, ncc)))
            conf_prec = conf
        else:
            s, conf = s_prec, float(min(conf_prec, max(0.0, ncc)) * 0.5)   # riuso: confidenza ridotta
        Minv = np.linalg.inv(_omografia(q, wc, hc))
        for n, (xl, xr, nero, c) in gr.items():
            y0, y1 = (ya, yb) if nero else (ya, hc - 1)
            pts = np.float32([[xl + s, y0], [xr + s, y0], [xr + s, y1], [xl + s, y1]]).reshape(-1, 1, 2)
            fp = cv2.perspectiveTransform(pts, Minv).reshape(4, 2)
            riq[n].append(RiquadroNota(
                nota=n, nome=nome_nota(n), nero=bool(nero), frame=i, t=round(i / fps, 6),
                x1=int(round(fp[:, 0].min())), y1=int(round(fp[:, 1].min())),
                x2=int(round(fp[:, 0].max())), y2=int(round(fp[:, 1].max())),
                visibile=True, confidenza=round(conf, 3)))
        i += 1
    cap.release()
    s = SagomeVideo(video=Path(str(video)).name, fps=fps, n_frame=i, quad=quad_out,
                    riquadri=riq, visibili=note_vis, ottava=ottava)
    s.ottava["prova"]["geometria_canonica"] = {"wc": wc, "hc": hc, "banda_neri": [ya, yb],
                                               "span_tastiera": list(m["span"])}
    return s


# ------------------------------------------------------------ 3. clip
def _crop(frame, r: RiquadroNota, dim: tuple[int, int], margine: float = 0.25):
    """Crop della nota (riquadro + margine), ridimensionato a `dim` = (larghezza, altezza)."""
    h, w = frame.shape[:2]
    mx, my = (r.x2 - r.x1) * margine, (r.y2 - r.y1) * margine
    x1, x2 = int(max(0, r.x1 - mx)), int(min(w, r.x2 + mx))
    y1, y2 = int(max(0, r.y1 - my)), int(min(h, r.y2 + my))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return np.zeros((dim[1], dim[0], 3), np.uint8)
    return cv2.resize(frame[y1:y2, x1:x2], dim, interpolation=cv2.INTER_AREA)


# ------------------------------------------------------- scrittura video
class ScrittoreVideo:
    """Frame BGR -> mp4 H.264/yuv420p (stesso schema di `pipeline.ScrittoreFfmpeg`).

    Il `VideoWriter` di OpenCV col tag `mp4v` scrive MPEG-4 Part 2: Chrome/Chromium non
    lo decodificano e mostrano il tasto play in grigio, quindi i video di controllo si
    scrivono con ffmpeg. Se ffmpeg non c'e' si ripiega su mp4v, che resta leggibile con
    VLC/QuickTime ma non nelle pagine dello Studio web.
    """

    def __init__(self, path: Path, larghezza: int, altezza: int, fps: float) -> None:
        self.percorso = Path(path)
        self.larghezza, self.altezza = int(larghezza), int(altezza)
        self.guasto = False
        self.h264 = False
        exe = shutil.which("ffmpeg") or ("/opt/homebrew/bin/ffmpeg"
                                         if Path("/opt/homebrew/bin/ffmpeg").exists() else None)
        self._vw = None
        if exe:
            self.h264 = True
            # -movflags +faststart mette l'indice (moov) in testa: il browser comincia a
            # riprodurre senza scaricare tutto il file. -vf pad raddoppia i lati dispari
            # che yuv420p non accetta.
            cmd = [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                   "-s", f"{self.larghezza}x{self.altezza}", "-r", f"{fps:.6f}", "-i", "-",
                   "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-an",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
                   "-crf", "23", "-movflags", "+faststart", str(self.percorso)]
            self._p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        else:
            self._p = None
            self._vw = cv2.VideoWriter(str(self.percorso), cv2.VideoWriter_fourcc(*"mp4v"),
                                       float(fps), (self.larghezza, self.altezza))

    def scrivi(self, frame: np.ndarray) -> None:
        if self.guasto:
            return
        if frame.shape[1] != self.larghezza or frame.shape[0] != self.altezza:
            frame = cv2.resize(frame, (self.larghezza, self.altezza))
        if self._vw is not None:
            self._vw.write(frame)
            return
        try:
            self._p.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
        except (BrokenPipeError, OSError):
            self.guasto = True

    def chiudi(self) -> None:
        """Chiude ffmpeg (o il writer di OpenCV). Va chiamata sempre, anche in caso di errore."""
        if self._vw is not None:
            self._vw.release()
            return
        try:
            self._p.stdin.close()
        except OSError:
            pass
        self._p.wait()

    def __del__(self) -> None:                # rete di sicurezza se il chiamante esce per errore
        try:
            self.chiudi()
        except Exception:
            pass


def _dim_clip(rs: list) -> tuple[int, int]:
    w = float(np.median([r.x2 - r.x1 for r in rs])) * 1.5
    h = float(np.median([r.y2 - r.y1 for r in rs])) * 1.5
    return int(max(16, 2 * round(w / 2))), int(max(16, 2 * round(h / 2)))


def scrivi_clip_per_nota(s: SagomeVideo, video, cartella, *, formato: str = "mp4") -> list[Path]:
    """
    UNA clip per nota inquadrata, lunga TUTTO il video (n_frame frame), con dentro SOLO
    il crop di quella nota (riquadro + 25% di margine, dimensione fissa per clip).
    formato: "mp4" (H.264 via ffmpeg, ripiego mp4v di OpenCV) | "jpeg" (cartella per nota).
    Le note non inquadrate non hanno clip. Il video viene riletto a gruppi di 8 note.
    """
    if formato not in ("mp4", "jpeg"):
        raise ValueError("formato deve essere 'mp4' o 'jpeg'")
    cart = Path(cartella)
    cart.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg")
    dims = {n: _dim_clip(s.riquadri[n]) for n in s.visibili}
    scritti: list[Path] = []
    for gruppo in [s.visibili[k:k + 8] for k in range(0, len(s.visibili), 8)]:
        procs: dict = {}
        for n in gruppo:
            w, h = dims[n]
            if formato == "jpeg":
                (cart / f"{n:03d}").mkdir(exist_ok=True)
                procs[n] = None
            elif ff:
                procs[n] = subprocess.Popen(
                    [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                     "-s", f"{w}x{h}", "-r", f"{s.fps:.6f}", "-i", "-", "-an", "-c:v", "libx264",
                     "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "veryfast",
                     str(cart / f"{n:03d}.mp4")], stdin=subprocess.PIPE)
            else:
                procs[n] = cv2.VideoWriter(str(cart / f"{n:03d}.mp4"),
                                           cv2.VideoWriter_fourcc(*"mp4v"), s.fps, (w, h))
        cap = _apri(video)
        for i in range(s.n_frame):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"il video ha meno frame di quelli attesi ({i} < {s.n_frame})")
            for n in gruppo:
                crop = _crop(frame, s.riquadri[n][i], dims[n])
                if formato == "jpeg":
                    cv2.imwrite(str(cart / f"{n:03d}" / f"{i:06d}.jpg"), crop,
                                [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                elif ff:
                    procs[n].stdin.write(crop.tobytes())
                else:
                    procs[n].write(crop)
        cap.release()
        for n in gruppo:
            p = procs[n]
            if formato == "mp4":
                if ff:
                    p.stdin.close()
                    if p.wait() != 0:
                        raise RuntimeError(f"ffmpeg ha fallito sulla clip della nota {n}")
                else:
                    p.release()
            scritti.append(cart / f"{n:03d}.mp4" if formato == "mp4" else cart / f"{n:03d}")
    return scritti


# ------------------------------------------------------- serializzazione
def salva_sagome(s: SagomeVideo, path) -> Path:
    """sagome.json: riquadri per nota in colonne (x1,y1,x2,y2,confidenza), niente NaN."""
    doc = {
        "video": s.video, "fps": round(s.fps, 6), "n_frame": s.n_frame,
        "quad": [[[round(x, 2), round(y, 2)] for x, y in q] for q in s.quad],
        "visibili": s.visibili, "ottava": s.ottava,
        "riquadri": {str(n): {"nero": rs[0].nero, "nome": rs[0].nome,
                              "x1": [r.x1 for r in rs], "y1": [r.y1 for r in rs],
                              "x2": [r.x2 for r in rs], "y2": [r.y2 for r in rs],
                              "confidenza": [r.confidenza for r in rs],
                              "visibile": [r.visibile for r in rs]}
                     for n, rs in s.riquadri.items()},
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return p


def carica_sagome(path) -> SagomeVideo:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    fps = float(d["fps"])
    riq = {}
    for k, c in d["riquadri"].items():
        n = int(k)
        riq[n] = [RiquadroNota(nota=n, nome=c["nome"], nero=bool(c["nero"]), frame=i,
                               t=round(i / fps, 6), x1=c["x1"][i], y1=c["y1"][i], x2=c["x2"][i],
                               y2=c["y2"][i], visibile=bool(c["visibile"][i]),
                               confidenza=c["confidenza"][i]) for i in range(len(c["x1"]))]
    quad = [[(float(x), float(y)) for x, y in q] for q in d["quad"]]
    return SagomeVideo(video=d["video"], fps=fps, n_frame=int(d["n_frame"]), quad=quad,
                       riquadri=riq, visibili=[int(n) for n in d["visibili"]], ottava=d["ottava"])

````

### `motore_prospettica.py`

````python
"""
Motore prospettico — griglia dei tasti stimata frame per frame dal modello
`griglia_prospettica.py` (ripresa a mano libera) e decisione premuto/rilasciato
dentro i riquadri per nota (la stessa misura del motore calibrato).

    python3 motore_prospettica.py video.mp4 -o out/ [--nota-gruppo2 61] [--prima-nota 48]
        [--cartella-sagome DIR] [--formato-clip mp4|jpeg] [--senza-clip]
        [--senza-video-griglia] [--json-griglia]

Perche' non servono YOLO ne' mediapipe
-------------------------------------
La tastiera e' un oggetto rigido con una griglia regolare: il modello stima per ogni
frame un'omografia (spazio canonico in larghezze di tasto bianco -> immagine) usando i
tasti neri veri, il fondo dei neri e il feltro rosso, poi la insegue con il flusso
ottico. Da qui si ricavano i riquadri di OGNI tasto in ogni frame, come nel motore
calibrato: nessun modello neurale, solo cv2 + numpy, e la griglia segue i movimenti
della ripresa a mano libera (i riquadri restano sui tasti anche quando la tastiera si
sposta nell'inquadratura).

Uscita (identica al motore calibrato, cosi' lo Studio web la mostra senza casi speciali)
---------------------------------------------------------------------------------------
    out/notes.json          eventi nota + meta + blocco "prospettica"
    out/song.mid            MIDI
    out/prima_griglia.jpg   primo frame con la griglia del modello (blu = tasti neri)
    out/griglia.mp4         tutto il video con la griglia disegnata, in H.264 (controllo visivo
                            frame per frame: si riproduce nel browser). Nei frame in cui il
                            modello segna un tasto come premuto il tasto viene scurito da un
                            velo semitrasparente: l'evento si vede senza perdere lo sfondo
    out/griglia.json        (--json-griglia) poligoni e celle per frame, come il modello
    sagome/sagome.json      riquadri per nota in colonne (riuso con --cartella-sagome)
    sagome/<nota>.mp4       clip della nota (una clip per tasto, per il controllo umano)

Limiti dichiarati
-----------------
* L'ottava dei tasti non e' deducibile dalla sola immagine: il modello la fissa con
  `--nota-gruppo2` (default 61 = C#4, il primo nero del gruppo da due piu' vicino al
  centro). `--prima-nota 50` (D3) corregge l'ottava senza cambiare la geometria.
* Le note non inquadrate nel primo frame non esistono in uscita: non possono comparire
  nel MIDI (stessa regola del motore calibrato).
* Vale il limite 2D del motore calibrato: un dito che sfiora un tasto cambia l'immagine
  come un dito che preme; le soglie vanno tarate sul video reale.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

import griglia_prospettica as G
from motore_calibrato import RilevatoreCalibrato
from sagome import (RiquadroNota, SagomeVideo, ScrittoreVideo, carica_sagome, salva_sagome,
                    scrivi_clip_per_nota)
from to_midi import riepiloga, salva_json, salva_midi

QUOTA_VISIBILE = 0.60      # quota minima del tasto dentro il frame per dire "inquadrato"
LATO_MIN = 6               # lato minimo (px) del riquadro per potervi misurare dentro
_HC = _WC = 100            # spazio canonico di riferimento per la zona di analisi
_VEL_MAX = 20.0            # inlier di `affina` che valgono confidenza 1.0
_SOGLIA_FERMO = 0.05       # differenza media (livelli di grigio) sotto cui il frame e' "fermo"
_SOGLIA_TAGLIO = 38.0      # differenza media (livelli) sopra cui si SOSPETTA un cambio di
                           # inquadratura. Misurato: uno stacco vero fra due riprese sta a 60+,
                           # mentre una mano che passa davanti o una luce che cambia sta a 20-30.
                           # Con la soglia a 20 (valore precedente) un movimento brusco rifaceva la
                           # griglia da zero: 8 falsi tagli in 20 frame sul video verticale di prova.
_SOGLIA_PIXEL = 25.0       # differenza (livelli) sotto cui due pixel sono "lo stesso punto"
_QUOTA_IMPRONTA = 0.72     # quota di punti dell'impronta che deve combaciare per dire "fermo"

# --- guardie sul cambio di inquadratura: un taglio si adotta solo se e' convincente ---------
# Il sospetto da solo non basta: quando la differenza di frame supera `_SOGLIA_TAGLIO` la griglia
# NON viene piu' rifatta subito. Resta "in verifica" finche' non si dimostra che la nuova scena
# e' una tastiera e che e' la stessa per piu' frame di fila:
_CONFERME_TAGLIO = 3       # frame in cui il nuovo anchor deve concordare con se stesso
_TAGLIO_ACCORDO = 0.15     # accordo fra due anchor: scarto max (frazione di larghezza tastiera)
_TAGLIO_TENUE = 0.30       # salto oltre cui il nuovo anchor e' "sospetto" e pretende piu' prove
_TAGLIO_MIN_EVIDENZA = 0.80        # evidenza "ottima" di un nuovo anchor sospetto
_TAGLIO_MARGINE_EVIDENZA = 0.05    # ...oppure un'evidenza non peggiore di cosi' rispetto alla
                                   # griglia in uso: nei video scuri/obliqui la tastiera VERA sta
                                   # a 0.62-0.79 (misurato), quindi il solo 0.80 assoluto
                                   # bloccherebbe anche i tagli veri
_TAGLIO_OSTINATO = 15      # se il candidato regge comunque per tanti frame, lo si adotta: la
                           # scena e' cambiata davvero e attendere oltre non serve
_TAGLIO_ATTESA = 45        # frame di verifica dopo i quali si smette di cercare un nuovo anchor
                           # (la scena non si stabilizza: si continua a tracciare la griglia)
_ATTESA_STAMPA = 15        # ogni quanti frame, mentre si e' in verifica, si stampa il log

_TINTA_PREMUTO = (0.75, 0.60, 0.60)   # BGR: fattori del tasto premuto. Tutti < 1 = il tasto
                                      # si scurisce; il blu cala meno degli altri = resta una
                                      # tinta fredda. Moltiplicare (invece di miscelare verso un
                                      # colore fisso) conserva il contrasto dello sfondo sotto il
                                      # velo e non schiarisce i tasti neri, che restano neri.
_TASTI = set(G.BIANCHI) | set(G.NERI)   # note del modello: i soli tasti che si possono scurire
_FATT_PREMUTO = np.array(_TINTA_PREMUTO, np.float32)


def _scurisci(o: np.ndarray, mask: np.ndarray) -> None:
    """Scurisce i pixel sotto `mask` (in place), lasciando passare lo sfondo attenuato.

    Si lavora solo sul rettangolo che contiene la maschera, cosi' il costo non dipende
    dalla risoluzione del video. `mask` e' antialiasata (cv2.LINE_AA): l'effetto sfuma
    sui bordi del tasto.
    """
    y, x = np.where(mask > 0)
    if not len(y):
        return
    y1, y2, x1, x2 = int(y.min()), int(y.max()) + 1, int(x.min()), int(x.max()) + 1
    regione = o[y1:y2, x1:x2].astype(np.float32)
    m = (mask[y1:y2, x1:x2].astype(np.float32) / 255.0)[..., None]
    fattore = 1.0 - m * (1.0 - _FATT_PREMUTO)          # m=0 -> 1 (intatto); m=1 -> la tinta
    np.clip(regione * fattore, 0, 255, out=regione)
    o[y1:y2, x1:x2] = regione.astype(np.uint8)


# --------------------------------------------------------------- disegno
def disegna(frame: np.ndarray, H: np.ndarray, offset: int = 0, etichette: bool = True,
            premuti: set[int] | None = None) -> np.ndarray:
    """Come `griglia_prospettica._disegna`, con le etichette corrette (+offset semitoni).

    Blù (255,160,30 BGR) = tasti neri, verde = tasti bianchi: gli stessi colori del
    modello, cosi' il video di controllo e' identico a quello di riferimento.

    `premuti` (note in semitoni, come in `notes.json`) sono i tasti che il modello segna
    come premuti *in questo frame*: ognuno viene scurito da un velo semitrasparente, cosi'
    il video di controllo mostra gli stessi eventi del MIDI lasciando vedere lo sfondo.
    """
    o = frame.copy()
    h, w = frame.shape[:2]
    if premuti:
        mask = None
        for n in premuti:
            m = n - offset                              # da semitoni finali al lessico del modello
            if m not in _TASTI:
                continue
            pol = G.poligono_tasto(H, m)
            if not np.isfinite(pol).all():
                continue
            if pol[:, 0].max() < 0 or pol[:, 0].min() > w or pol[:, 1].max() < 0 or pol[:, 1].min() > h:
                continue                                # tasto fuori inquadratura
            if mask is None:
                mask = np.zeros((h, w), np.uint8)
            cv2.fillPoly(mask, [np.int32(pol).reshape(-1, 1, 2)], 255, cv2.LINE_AA)
        if mask is not None:                            # una sola passata per frame, non una per tasto
            _scurisci(o, mask)
    for n, col in ((G.BIANCHI, (60, 220, 60)), (G.NERI, (255, 160, 30))):
        for m in n:
            pol = G.poligono_tasto(H, m)
            if not np.isfinite(pol).all():
                continue
            if pol[:, 0].max() < 0 or pol[:, 0].min() > w or pol[:, 1].max() < 0 or pol[:, 1].min() > h:
                continue                                   # tasto fuori inquadratura
            cv2.polylines(o, [np.int32(pol)], True, col, 2, cv2.LINE_AA)
    if not etichette:
        return o
    for m in G.BIANCHI:
        p = G.poligono_tasto(H, m)
        x, y = (p[2] + p[3]) / 2.0
        if 0 < x < w - 14 and 0 < y < h - 4:
            t = G.nome(m + offset)
            pos = (int(x) - 8 * len(t) // 2 - 3, int(y) - 10)
            cv2.putText(o, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(o, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return o


# ------------------------------------------------------------ geometria
def _flusso(prev: np.ndarray, cur: np.ndarray, H_prev: np.ndarray) -> np.ndarray:
    """Come `griglia_prospettica.flusso`, ma senza fidarsi di un flusso degenere.

    Su una scena ferma (telefono appoggiato, video ripetuto, tasti non in movimento) i
    punti tracciati non si spostano: l'omografia stimata su corrispondenze identiche e'
    degenere e cambia da frame a frame, facendo VAGARE la griglia (e quindi riquadri
    diversi sullo stesso pixel) e inventando note. Se il flusso e' degenere si tiene la
    griglia precedente e sara' `affina` a misurarla di nuovo sull'immagine.
    """
    m = G.maschera_tastiera(H_prev, prev.shape)
    p0 = cv2.goodFeaturesToTrack(prev, 400, 0.01, 6, mask=m)
    if p0 is None or len(p0) < 12:
        return np.eye(3)
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, p0, None, winSize=(31, 31), maxLevel=4)
    ok = st.ravel() == 1
    if int(ok.sum()) < 12:
        return np.eye(3)
    a, b = p0[ok].reshape(-1, 2), p1[ok].reshape(-1, 2)
    spost = float(np.median(np.linalg.norm(b - a, axis=1)))
    if spost < 0.15:                                  # immagine ferma: flusso inutile
        return np.eye(3)
    Hf, mask = cv2.findHomography(a, b, cv2.RANSAC, 3.0)
    if (Hf is None or not np.isfinite(Hf).all() or int(np.sum(mask)) < 12
            or not np.isfinite(np.linalg.det(Hf[:2, :2]))
            or abs(float(np.linalg.det(Hf[:2, :2])) - 1.0) > 0.5):
        return np.eye(3)                              # omografia schiacciata/assurda
    return Hf


def _dentro(pol: np.ndarray, w: int, h: int) -> tuple[float, tuple[int, int, int, int]]:
    """Quota del poligono dentro il frame e riquadro (x1,y1,x2,y2) della parte visibile."""
    a_pol = float(abs(cv2.contourArea(np.float32(pol))))
    if a_pol < 1.0:
        return 0.0, (0, 0, 0, 0)
    rect = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    a_int, pol_int = cv2.intersectConvexConvex(np.float32(pol), rect)
    if pol_int is None or not np.size(pol_int) or float(a_int) < 1.0:
        return 0.0, (0, 0, 0, 0)
    p = pol_int.reshape(-1, 2)
    box = (int(np.floor(p[:, 0].min())), int(np.floor(p[:, 1].min())),
           int(np.ceil(p[:, 0].max())), int(np.ceil(p[:, 1].max())))
    return min(1.0, float(a_int) / a_pol), box


def _griglia(video, out: Path, *, nota_gruppo2: int = 61, prima_nota: int | None = None,
             max_secondi: float | None = None, json_griglia: bool = False,
             soglia_vis: float = QUOTA_VISIBILE,
             etichette: bool = True) -> tuple[SagomeVideo, np.ndarray, int]:
    """Stima la griglia per ogni frame e la impacchetta come `SagomeVideo`.

    Ritorna (sagome, H del primo frame, scarto d'ottava applicato in semitoni). La griglia
    per frame finisce in `sagome.H_serie`: e' quello che serve a `scrivi_video_griglia`, che
    e' l'unico posto dove si scrive `griglia.mp4` — dopo la decisione, perche' solo allora si
    sa quali tasti scurire frame per frame.
    """
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"impossibile aprire il video: {video}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_tot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    limite = int(max_secondi * fps) if max_secondi else None
    if limite is not None and n_tot:
        n_tot = min(n_tot, limite)
    H: np.ndarray | None = None
    H0 = np.eye(3, dtype=np.float64)
    H_anc: np.ndarray | None = None                  # griglia del primo frame (ancora)
    impronta: np.ndarray | None = None               # pixel dell'ancora sui punti campione
    punti: list[tuple[float, float]] = []
    neri_mod: list[int] = []
    bianchi_mod: list[int] = []
    prev: np.ndarray | None = None
    base_visibili: list[int] = []                    # note nel lessico del modello
    riq: dict[int, list[RiquadroNota]] = {}
    quad_lista: list[list[tuple[float, float]]] = []
    H_list: list[np.ndarray] = []
    visibili: list[int] = []
    delta, u0, u1, i = 0, -12.0, 12.0, 0
    k_prec, statici, tagli = 0, 0, 0                 # inlier ultimo frame; fermi; cambi scena
    cand: np.ndarray | None = None                   # griglia candidata in attesa di conferma
    cand_conferme, attesa = 0, 0                     # frame concordi sul candidato; frame di verifica
    diff_cand, conferme_taglio = 0.0, 1              # differenza e conferme del taglio da stampare
    while True:
        if limite is not None and i >= limite:
            break
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        fermo = False
        nuovo = H is None
        if not nuovo:
            diff = float(np.mean(np.abs(prev.astype(np.int16) - g.astype(np.int16))))
            fermo = diff < _SOGLIA_FERMO
            nuovo = diff >= _SOGLIA_TAGLIO
            if not nuovo:
                Hp = H if fermo else _flusso(prev, g, H) @ H
        sospetto = nuovo or cand is not None          # cambio di scena: vero o solo presunto
        adottata = False
        if sospetto:                                 # la griglia si rifa' solo dopo verifica
            if nuovo and H is not None:   # in un frame sospetto non c'e' una predizione di flusso
                Hp = H                    # fresca: si riparte dalla griglia precedente
            Hs, k2 = _ancora(f, g, nota_gruppo2)
            if Hs is None:
                if H is None:
                    raise RuntimeError("neri insufficienti sul primo frame: inquadra la tastiera")
                print(f"[prospettica] frame {i}: cambio di scena ma griglia non ritrovata: "
                      f"tengo la precedente", flush=True)
                cand, cand_conferme, attesa = None, 0, 0
            elif H is None:                          # primo frame: non c'e' nessuna storia
                adottata = True
            else:
                # Fix B: la stessa scena deve reggere per piu' frame di fila. Una mano che passa
                # davanti o una luce che cambia danno un anchor diverso a ogni frame (non regge);
                # uno stacco vero invece si rifa' identico frame dopo frame.
                if cand is not None and _distanza_griglie(cand, Hs) <= _TAGLIO_ACCORDO:
                    cand_conferme += 1
                else:
                    cand_conferme, attesa = 1, 0      # ancora instabile: si riparte da zero
                    diff_cand = diff                  # differenza che ha fatto scattare il sospetto
                cand = Hs
                attesa += 1
                if attesa > _TAGLIO_ATTESA:          # la scena non si stabilizza: non e' un taglio
                    print(f"[prospettica] frame {i}: la scena non si stabilizza ({attesa} frame): "
                          f"smetto di cercare un nuovo anchor, continuo a tracciare la griglia",
                          flush=True)
                    cand, cand_conferme, attesa = None, 0, 0
                elif cand_conferme >= _CONFERME_TAGLIO:
                    # Fix C: il salto e' credibile solo se la scena nuova "spiega" i tasti almeno
                    # quanto quella in uso. Se il candidato insiste per `_TAGLIO_OSTINATO` frame
                    # si adotta comunque: la scena e' cambiata davvero.
                    seg_c = _visibili_di(Hs, w, h, soglia_vis)
                    ev_new = _evidenza(g, Hs, [n for n in seg_c if G.e_nero(n)],
                                       [n for n in seg_c if not G.e_nero(n)], G._soglia(g))
                    ev_old = (_evidenza(g, H, neri_mod, bianchi_mod, G._soglia(g))
                              if neri_mod or bianchi_mod else 0.0)
                    salto = _distanza_griglie(H, Hs)
                    if (salto > _TAGLIO_TENUE and cand_conferme < _TAGLIO_OSTINATO
                            and ev_new < _TAGLIO_MIN_EVIDENZA
                            and ev_new < ev_old - _TAGLIO_MARGINE_EVIDENZA):
                        if attesa <= 3 or attesa % _ATTESA_STAMPA == 0:
                            print(f"[prospettica] frame {i}: salto {salto:.2f} larghezze "
                                  f"tastiera, evidenza {ev_new:.2f} contro {ev_old:.2f} della "
                                  f"griglia in uso: anchor sospetto, tengo la precedente "
                                  f"({cand_conferme} conferme)", flush=True)
                    else:
                        adottata = True
                elif attesa <= 3 or attesa % _ATTESA_STAMPA == 0:
                    print(f"[prospettica] frame {i}: nuovo anchor in verifica "
                          f"({cand_conferme}/{_CONFERME_TAGLIO} conferme, salto "
                          f"{_distanza_griglie(H, Hs):.2f} larghezze tastiera): tengo la griglia "
                          f"precedente", flush=True)
            if adottata:
                H = Hp = np.float64(Hs)
                k = k2
                conferme_taglio = cand_conferme
                cand, cand_conferme, attesa = None, 0, 0
                seg = _visibili_di(H, w, h, soglia_vis)
                if len(seg) < 4:
                    raise RuntimeError(f"solo {len(seg)} tasti inquadrati: inquadra meglio "
                                       f"la tastiera")
                neri_mod = [n for n in seg if G.e_nero(n)]
                bianchi_mod = [n for n in seg if not G.e_nero(n)]
                if not base_visibili:            # primo segmento del video
                    H0 = H
                    base_visibili = seg
                    if prima_nota is not None:
                        delta = _delta_ottava(base_visibili, prima_nota)
                    visibili = sorted(n + delta for n in base_visibili)
                    riq = {n: [] for n in visibili}
                    ub = [G.u_bianco(n) for n in bianchi_mod]
                    u0, u1 = (min(ub) - 0.1, max(ub) + 1.1) if ub else (-12.0, 12.0)
                    print(f"[prospettica] primo frame: {len(base_visibili)} tasti inquadrati, "
                          f"note {min(visibili)}..{max(visibili)}"
                          + (f", ottave {delta // 12:+d}" if delta else ""), flush=True)
                else:                            # taglio: la griglia riparte da zero
                    tagli += 1
                    nuovi = [n for n in seg if (n + delta) not in riq]
                    for n in nuovi:              # riquadri vuoti per i frame gia' passati
                        nv = n + delta
                        riq[nv] = [RiquadroNota(nota=nv, nome=G.nome(nv), nero=G.e_nero(n),
                                                frame=j, t=round(j / fps, 6), x1=0, y1=0,
                                                x2=0, y2=0, visibile=False, confidenza=0.0)
                                   for j in range(i)]
                    base_visibili += nuovi
                    visibili = sorted(riq)
                    print(f"[prospettica] frame {i}: cambio di inquadratura confermato "
                          f"({diff_cand:.0f} livelli, {conferme_taglio} frame concordi): "
                          f"griglia rifatta, {len(seg)} tasti inquadrati "
                          f"({len(nuovi)} nuovi)", flush=True)
                punti = _punti_impronta(neri_mod, bianchi_mod)
                H_anc = H.copy()                 # ancora del segmento
                impronta = _campiona(g, H_anc, punti)
                k_prec = k
        if not adottata:                         # nessun cambio di scena: si traccia come sempre
            if fermo:                            # immagine identica: la geometria non cambia
                k = k_prec
                H = Hp
            elif (impronta is not None
                  and _stessa_scena(g, impronta, H_anc, punti, _QUOTA_IMPRONTA)):
                k = k_prec                       # tastiera ferma: vale la griglia del segmento
                H = H_anc
                statici += 1
            else:
                H2, k = G.affina(g, Hp, G.rosso(f), 3)
                if H2 is not None and k >= 10:
                    H = np.float64(H2)
                else:
                    H = Hp
                k_prec = k
        prev = g
        conf = round(float(min(1.0, max(0.0, k / _VEL_MAX))), 3)
        for n_model in base_visibili:
            quota, box = _dentro(G.poligono_tasto(H, n_model), w, h)
            n = n_model + delta
            riq[n].append(RiquadroNota(
                nota=n, nome=G.nome(n), nero=G.e_nero(n_model), frame=i, t=round(i / fps, 6),
                x1=box[0], y1=box[1], x2=box[2], y2=box[3],
                visibile=bool(quota >= soglia_vis and (box[2] - box[0]) >= LATO_MIN
                              and (box[3] - box[1]) >= LATO_MIN),
                confidenza=conf))
        q4 = G.proietta(H, [(u0, 0), (u1, 0), (u1, G.LW), (u0, G.LW)])
        quad_lista.append([(float(x), float(y)) for x, y in q4])
        H_list.append(H.copy())
        if i == 0:                                   # anteprima: il video completo si scrive dopo
            cv2.imwrite(str(out / "prima_griglia.jpg"), disegna(f, H, delta, etichette))
        if i % 30 == 0:
            print(f"[prospettica] frame {i}: inlier {k}, tasti inquadrati "
                  f"{sum(1 for n in riq if riq[n][-1].visibile)}, "
                  f"evidenza {_evidenza(g, H, neri_mod, bianchi_mod, G._soglia(g)):.2f}, "
                  f"tastiera ferma {'si' if statici and H is H_anc else 'no'}", flush=True)
        i += 1
    cap.release()
    if statici:
        print(f"[prospettica] {statici} frame con la tastiera identica all'ancora del segmento: "
              f"usata quella (niente deriva)", flush=True)
    if tagli:
        print(f"[prospettica] {tagli} cambi di inquadratura confermati: la griglia e' stata rifatta "
              f"da zero",
              flush=True)
    if i == 0 or not riq:
        raise RuntimeError("nessun frame utilizzabile nel video")
    if json_griglia:
        doc_g: list[dict] = []
        for j, Hj in enumerate(H_list):
            tasti = {}
            for n_model in base_visibili:
                n = n_model + delta
                tasti[str(n)] = {"nome": G.nome(n), "nero": G.e_nero(n_model),
                                 "poligono": np.round(G.poligono_tasto(Hj, n_model), 1).tolist(),
                                 "celle_profondita": [np.round(c, 1).tolist()
                                                      for c in G._celle(Hj, n_model, 3)]}
            doc_g.append({"frame": j, "t": round(j / fps, 4), "tasti": tasti})
        (out / "griglia.json").write_text(json.dumps(
            {"video": Path(str(video)).name, "fps": round(fps, 6), "n_frame": i,
             "modello": {"LB": G.LB, "LW": G.LW, "BW": G.BW,
                         "offset_ottave": delta // 12, "nota_gruppo2": nota_gruppo2},
             "frames": doc_g}, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    ub = [G.u_bianco(n) for n in base_visibili if not G.e_nero(n)] or [-12.0, 12.0]
    g_can = {"wc": _WC, "hc": _HC, "banda_neri": [0, int(round(_HC * G.LB / G.LW))],
             "span_tastiera": [float(min(ub)), float(max(ub) + 1)]}
    ottava = {"scelta": min(visibili), "ambigua": False, "ipotesi_usata": None, "candidate": [],
              "scarto_ottave": delta // 12, "nota_gruppo2": nota_gruppo2,
              "prova": {"geometria_canonica": g_can}}
    s = SagomeVideo(video=Path(str(video)).name, fps=fps, n_frame=i, quad=quad_lista,
                    riquadri=riq, visibili=visibili, ottava=ottava, H_serie=H_list)
    return s, H0, delta


# ------------------------------------------------- video con i tasti premuti
def _serie_premuti(eventi, n_frame: int) -> list[set[int]]:
    """Per ogni frame, le note (semitoni come in `notes.json`) che un evento copre.

    Un evento vale dal frame di attacco all'ultimo frame premuto: sono esattamente i frame
    in cui il modello dice "premuto", cioe' gli stessi che finiscono nel MIDI.
    """
    serie: list[set[int]] = [set() for _ in range(n_frame)]
    for e in eventi:
        for i in range(max(0, e.frame_onset), min(n_frame, e.frame_offset + 1)):
            serie[i].add(e.nota)
    return serie


def scrivi_video_griglia(video, out: Path, sagome: SagomeVideo, eventi, *, delta: int = 0,
                         etichette: bool = True) -> Path | None:
    """(Ri)scrive `out/griglia.mp4`: la griglia su tutto il video e i tasti premuti scuriti.

    Va chiamata *dopo* la decisione (gli eventi esistono solo allora) e rilegge il video una
    volta. Senza `sagome.H_serie` — cioe' quando la griglia e' riusata da `sagome.json` — non
    c'e' modo di ridisegnarla: si avvisa e non si scrive nulla.
    """
    if not sagome.H_serie:
        print("[prospettica] griglia.mp4 non riscritto: la griglia e' stata riusata da "
              "sagome.json, manca l'omografia per frame", flush=True)
        return None
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise FileNotFoundError(f"impossibile aprire il video: {video}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    n = min(int(sagome.n_frame), len(sagome.H_serie))
    serie = _serie_premuti(eventi, n)
    vw = ScrittoreVideo(out / "griglia.mp4", w, h, fps)
    i = 0
    while i < n:
        ok, f = cap.read()
        if not ok:
            break
        vw.scrivi(disegna(f, sagome.H_serie[i], delta, etichette, serie[i]))
        i += 1
    cap.release()
    vw.chiudi()
    print(f"[prospettica] video di controllo: {out / 'griglia.mp4'} ({i} frame, "
          f"tasti premuti in evidenza)", flush=True)
    return out / "griglia.mp4"


def _evidenza(g: np.ndarray, H: np.ndarray, neri: list[int], bianchi: list[int],
              T: float) -> float:
    """Quanto la griglia (H) spiega l'immagine: tasti neri scuri, bianchi chiari.

    Non usa le corrispondenze interne del modello: campiona punti fissi dello spazio
    canonico (centro dei neri, fascia frontale dei bianchi) e guarda cosa c'e' sotto.
    Serve a distinguere una griglia giusta da una derivata/tiltata, che il conteggio
    degli inlier di RANSAC non vede (le misure sono fatte *attorno* alla predizione).
    """
    h, w = g.shape
    quote = ((neri, (0.8, 1.4, 2.0, 2.6, 3.2)), (bianchi, (G.LB + 0.35, G.LW - 0.35)))
    pezzi: list[float] = []
    for note, vs in quote:
        pts = [(G.u_nero(n) if (n % 12) in G._NERI_PC else G.u_bianco(n) + 0.5, v)
               for n in note for v in vs]
        if not pts:
            continue
        p = G.proietta(H, pts)
        dentro = (np.isfinite(p).all(axis=1) & (p[:, 0] >= 1) & (p[:, 0] < w - 1)
                  & (p[:, 1] >= 1) & (p[:, 1] < h - 1))
        if not dentro.any():
            continue
        p = p[dentro]
        pezzi.append(float((g[p[:, 1].astype(int), p[:, 0].astype(int)] < T).mean()))
    return float(np.mean(pezzi)) if pezzi else 0.0


def _punti_impronta(neri: list[int], bianchi: list[int]) -> list[tuple[float, float]]:
    """Punti canonici (centro dei neri, fascia frontale dei bianchi) per l'impronta."""
    pts: list[tuple[float, float]] = []
    for n in neri:
        pts += [(G.u_nero(n), v) for v in (0.9, 1.6, 2.3, 3.0)]
    for n in bianchi:
        pts += [(G.u_bianco(n) + 0.5, v) for v in (G.LB + 0.5, G.LB + 1.1, G.LW - 0.25)]
    return pts


def _campiona(g: np.ndarray, H: np.ndarray, pts: list[tuple[float, float]],
              fuori: float = -1.0) -> np.ndarray:
    """Valori di grigio nei punti (canonico) proiettati; -1 dove non c'e' immagine."""
    h, w = g.shape
    p = G.proietta(H, pts)
    out = np.full(len(pts), fuori, dtype=np.float32)
    if not np.isfinite(p).all():
        p = np.nan_to_num(p, nan=-10.0, posinf=-10.0, neginf=-10.0)
    dentro = (p[:, 0] >= 1) & (p[:, 0] < w - 1) & (p[:, 1] >= 1) & (p[:, 1] < h - 1)
    if dentro.any():
        q = p[dentro]
        out[dentro] = g[q[:, 1].astype(int), q[:, 0].astype(int)]
    return out


def _stessa_scena(g: np.ndarray, impronta: np.ndarray, H: np.ndarray,
                  punti: list[tuple[float, float]], soglia: float) -> bool:
    """La tastiera e' la stessa dell'ancora? (camera ferma: stessi pixel, stessi punti).

    Se i pixel sotto i punti dell'ancora sono quelli del primo frame, la geometria della
    tastiera NON e' cambiata: usare la griglia del primo frame e' corretto, e anzi evita
    che le misure frame-per-frame del modello facciano derivare la griglia (mani che
    coprono i tasti, RANSAC, flusso ottico degenere).
    """
    cur = _campiona(g, H, punti)
    ok = (cur >= 0) & (impronta >= 0)
    if int(ok.sum()) < 20:
        return False
    return float((np.abs(cur[ok] - impronta[ok]) < _SOGLIA_PIXEL).mean()) >= soglia


def _distanza_griglie(Ha: np.ndarray, Hb: np.ndarray) -> float:
    """Distanza fra due griglie, in frazione di larghezza di tastiera (0 = identiche).

    Proietta lo stesso ventaglio di punti canonici con le due omografie e prende la distanza
    MEDIANA fra le due proiezioni; la normalizza con l'ampiezza inquadrata di due ottave, cosi'
    il numero non dipende ne' dalla risoluzione ne' dalla distanza della tastiera. Serve a dire
    se due griglie descrivono la STESSA tastiera (accordo: sono l'una la continuazione
    dell'altra) oppure due tastiere diverse (una delle due e' un falso allarme).

    Si usa la proiezione, non i pixel: due griglie possono essere la stessa tastiera anche se
    il frame nel frattempo si e' mosso, mentre due falsi allarmi consecutivi (la "tastiera"
    trovata su una mano, su un'ombra) cadono in punti diversi dell'immagine.
    """
    pts = [(float(u), float(v)) for u in (-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0)
           for v in (0.5, G.LW / 2.0, G.LW - 0.5)]
    pa, pb = G.proietta(Ha, pts), G.proietta(Hb, pts)
    if not (np.isfinite(pa).all() and np.isfinite(pb).all()):
        return float("inf")
    amp = [float(np.linalg.norm(G.proietta(Hx, [(6.0, G.LW / 2.0)])[0]
                               - G.proietta(Hx, [(-6.0, G.LW / 2.0)])[0]))
           for Hx in (Ha, Hb)]
    if min(amp) < 1.0:                            # griglia degenere: nessun confronto possibile
        return float("inf")
    return float(np.median(np.linalg.norm(pa - pb, axis=1)) / (0.5 * sum(amp)))


def _ancora(f: np.ndarray, g: np.ndarray,
            nota_gruppo2: int) -> tuple[np.ndarray | None, int]:
    """Griglia assoluta del frame corrente (dall'immagine, senza storia): (H, inlier)."""
    try:
        H = np.float64(G.H_iniziale(f, nota_gruppo2))
    except (RuntimeError, ValueError):
        return None, 0
    H2, k = G.affina(g, H, G.rosso(f), 3)
    if H2 is not None and k >= 10:
        return np.float64(H2), int(k)
    return H, int(k)


def _visibili_di(H: np.ndarray, w: int, h: int, soglia: float) -> list[int]:
    """Note del modello che la griglia H mette (quasi) dentro il frame."""
    fuori = []
    for n in G.BIANCHI + G.NERI:
        quota, box = _dentro(G.poligono_tasto(H, n), w, h)
        if (quota >= soglia and (box[2] - box[0]) >= LATO_MIN and (box[3] - box[1]) >= LATO_MIN):
            fuori.append(n)
    return fuori


def _delta_ottava(visibili: list[int], prima_nota: int) -> int:
    """Scarto d'ottava (multiplo di 12) fra le etichette del modello e `prima_nota`.

    `prima_nota` = MIDI del tasto piu' a sinistra fra quelli inquadrati. Si confronta col
    tasto piu' a sinistra DELLO STESSO NOME che il modello vede: due tasti omonimi
    differiscono per un multiplo di 12, quindi la differenza dice di quante ottave il
    modello sbaglia (la geometria non cambia: cambiano solo le etichette).
    """
    stesso_nome = [n for n in visibili if (n - prima_nota) % 12 == 0]
    if stesso_nome:
        m = min(stesso_nome)                      # il piu' a sinistra con lo stesso nome
    else:
        m = min(visibili, key=lambda n: (abs((n - prima_nota + 6) % 12 - 6), n))
        print(f"[prospettica] avviso: nel video non si vede nessun {G.nome(prima_nota)}: "
              f"uso {G.nome(m)} come riferimento", flush=True)
    d = 12 * int(round((prima_nota - m) / 12.0))
    print(f"[prospettica] 'prima nota' {prima_nota} ({G.nome(prima_nota)}) contro "
          f"{m} ({G.nome(m)}) del modello: scarto d'ottava {d // 12:+d}", flush=True)
    return d


# -------------------------------------------------------------- rilevatore
class RilevatoreProspettico(RilevatoreCalibrato):
    """Premuto/rilasciato dentro i riquadri della griglia prospettica.

    Riusa la misura del motore calibrato (patch 6x10 della zona del tasto, mediana
    temporale come riposo, contrasto locale fra tasti vicini, isteresi): cambia solo la
    provenienza dei riquadri (qui il modello prospettico invece di `sagome`).
    """

    def __init__(self, sagome: SagomeVideo, H0: np.ndarray, *, delta: int = 0,
                 soglia_giu: float = 0.6, soglia_su: float = 0.4, finestra: int = 5) -> None:
        super().__init__(sagome, soglia_giu=soglia_giu, soglia_su=soglia_su, finestra=finestra)
        self.H0 = np.float64(H0)
        self.delta = int(delta)

    def _disegna(self, frame: np.ndarray) -> np.ndarray:
        o = disegna(frame, self.H0, self.delta)
        v = self.sagome.visibili
        txt = f"prospettica: {len(v)} note inquadrate ({min(v)}..{max(v)})"
        if self.delta:
            txt += f" · ottave {self.delta // 12:+d}"
        cv2.putText(o, txt, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(o, txt, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 235, 0), 1, cv2.LINE_AA)
        return o

    def analizza(self, video, out_dir, *, max_secondi=None, sagome_dir=None,
                 formato_clip: str = "mp4", scrivi_clip: bool = True,
                 video_griglia: bool = True) -> dict:
        r = super().analizza(video, out_dir, max_secondi=max_secondi, sagome_dir=sagome_dir,
                             formato_clip=formato_clip, scrivi_clip=scrivi_clip)
        p = Path(out_dir) / "notes.json"                    # rietichetta: e' un'altra griglia
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["motore"] = "prospettica"
        if "calibrato" in doc:
            doc["prospettica"] = doc.pop("calibrato")
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if video_griglia:            # ora si sa quali tasti scurire e in quali frame
            scrivi_video_griglia(video, Path(out_dir), self.sagome, self._eventi, delta=self.delta)
        return r


# ---------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Motore prospettico: griglia dei tasti per frame -> MIDI.")
    p.add_argument("video")
    p.add_argument("-o", "--output", default="out")
    p.add_argument("--nota-gruppo2", type=int, default=61,
                   help="nota del primo nero del gruppo da 2 neri piu' vicino al centro (61 = C#4)")
    p.add_argument("--prima-nota", type=int, default=None,
                   help="MIDI della prima nota visibile a sinistra: corregge l'ottava")
    p.add_argument("--soglia-giu", type=float, default=0.6)
    p.add_argument("--soglia-su", type=float, default=0.4)
    p.add_argument("--finestra", type=int, default=5)
    p.add_argument("--max-secondi", type=float, default=None)
    p.add_argument("--cartella-sagome", default=None,
                   help="dove scrivere/leggere sagome.json: se esiste, la griglia viene riusata")
    p.add_argument("--sagome-json", default=None, help="griglia gia' calcolata da usare")
    p.add_argument("--formato-clip", choices=("mp4", "jpeg"), default="mp4")
    p.add_argument("--senza-clip", action="store_true")
    p.add_argument("--senza-video-griglia", action="store_true",
                   help="non scrivere griglia.mp4 (niente video con i tasti premuti in evidenza)")
    p.add_argument("--json-griglia", action="store_true",
                   help="scrive anche griglia.json (poligoni e celle per frame)")
    a = p.parse_args(argv)
    t0 = time.time()
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    try:
        cap = cv2.VideoCapture(a.video)
        if not cap.isOpened():
            print(f"[ERRORE] impossibile aprire il video: {a.video}", file=sys.stderr)
            return 2
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        W, Hh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        print(f"[video] {a.video}: {W}x{Hh}, {fps:.3f} fps, {n} frame, passo=1")
        cache = (Path(a.sagome_json) if a.sagome_json
                 else Path(a.cartella_sagome or a.output) / "sagome.json")
        if cache.is_file():
            print(f"[prospettica] riuso la griglia gia' calcolata: {cache}")
            s = carica_sagome(cache)
            c2 = cv2.VideoCapture(a.video)
            ok, f0 = c2.read()
            c2.release()
            if not ok:
                raise RuntimeError("video illeggibile: non posso ricalcolare la griglia")
            H0 = np.float64(G.H_iniziale(f0, a.nota_gruppo2))
            delta = 12 * int(s.ottava.get("scarto_ottave") or 0)
        else:
            print(f"[prospettica] fase 1: griglia dei tasti frame per frame "
                  f"(nota_gruppo2={a.nota_gruppo2})")
            s, H0, delta = _griglia(a.video, out, nota_gruppo2=a.nota_gruppo2,
                                    prima_nota=a.prima_nota, max_secondi=a.max_secondi,
                                    json_griglia=a.json_griglia)
            salva_sagome(s, cache)
        v = s.visibili
        print(f"[griglia] estensione {min(v)}..{max(v)} ({len(v)} note inquadrate) - ottava dal "
              f"modello, scarto {delta // 12:+d} ottave")
        print("[prospettica] fasi 2-5: decisione, clip, uscita")
        r = RilevatoreProspettico(s, H0, delta=delta, soglia_giu=a.soglia_giu,
                                  soglia_su=a.soglia_su, finestra=a.finestra).analizza(
            a.video, a.output, sagome_dir=a.cartella_sagome, formato_clip=a.formato_clip,
            scrivi_clip=not a.senza_clip, video_griglia=not a.senza_video_griglia)
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        print(f"[ERRORE] {e}", file=sys.stderr)
        return 2
    print("\n=== RIEPILOGO ===")
    print(f"frame                 : {r['n_frame']}")
    print(f"note inquadrate       : {len(r['visibili'])}  emesse {len(r['emesse'])}")
    print(f"eventi nota           : {r['n_eventi']} (note uniche {r['riepilogo']['note_uniche']})")
    print(f"clip scritte          : {r['n_clip']}")
    print(f"tempo                 : {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

````

### `griglia_prospettica.py`

````python
"""
Griglia prospettica dei tasti, frame per frame (ripresa a mano libera).

Modello: spazio canonico (u, v) in LARGHEZZE DI TASTO BIANCO.
  u = 0 : bordo sinistro del Do centrale (C4); un bianco = 1 unita'.
  v = 0 : bordo posteriore dei tasti (dove partono i neri); v cresce verso il suonatore.
  neri  : v in [0, LB];   bianchi: v in [0, LW].
Per ogni frame si stima un'omografia H (canonico -> immagine) cosi':
  1. predizione: flusso ottico LK sui punti della tastiera (frame t-1 -> t);
  2. affinamento: si misurano i neri veri (righe scure) + fondo dei neri + feltro rosso
     e si ristima H con RANSAC.
Nessuna dipendenza oltre cv2 / numpy.
"""
from __future__ import annotations

import cv2
import numpy as np

NOMI = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_NERI_PC = {1: -0.10, 3: 0.10, 6: -0.12, 8: 0.0, 10: 0.12}      # come keyboard_grid._OFFSET_NERI
LB = 4.1          # lunghezza dei neri (in larghezze di bianco)
LW = 6.2          # lunghezza visibile dei bianchi
BW = 0.66         # larghezza del nero (in bianchi)
V_FELTRO = -0.08  # posizione v del feltro rosso
NOTA_MIN, NOTA_MAX = 36, 96
_SOGLIA_FERMO = 0.05      # differenza media (livelli) sotto cui l'immagine e' "ferma"
_SOGLIA_TAGLIO = 20.0     # differenza media sopra cui si ha un cambio di inquadratura


def e_nero(n): return (n % 12) in _NERI_PC
def nome(n): return f"{NOMI[n % 12]}{n // 12 - 1}"


def _indice_bianco(n):               # indice del bianco n rispetto a C4=0
    base = 60
    cont = 0
    if n >= base:
        return sum(1 for k in range(base, n) if not e_nero(k))
    return -sum(1 for k in range(n, base) if not e_nero(k))


def u_bianco(n):
    return float(_indice_bianco(n))


def u_nero(n):
    return _indice_bianco(n - 1) + 1 + _NERI_PC[n % 12]


NERI = [n for n in range(NOTA_MIN, NOTA_MAX + 1) if e_nero(n)]
BIANCHI = [n for n in range(NOTA_MIN, NOTA_MAX + 1) if not e_nero(n)]


def proietta(H, pts):
    p = np.float32(pts).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(p, H).reshape(-1, 2)


def poligono_tasto(H, n, lw=LW, lb=LB, bw=BW):
    if e_nero(n):
        uc = u_nero(n)
        c = [(uc - bw / 2, 0), (uc + bw / 2, 0), (uc + bw / 2, lb), (uc - bw / 2, lb)]
    else:
        u = u_bianco(n)
        c = [(u, 0), (u + 1, 0), (u + 1, lw), (u, lw)]
    return proietta(H, c)


def _soglia(g):
    return 0.62 * float(np.percentile(g, 90))


def _runs(mask):
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def _scala_px(H, u, v):
    a = proietta(H, [(u, v), (u + 1, v)])
    return float(np.linalg.norm(a[1] - a[0]))


def _dentro(p, w, h, m=0):
    return -m <= p[0] < w + m and -m <= p[1] < h + m


def misure(g, H, T, red=None):
    """Correspondenze (canonico, immagine) misurate attorno alla predizione H."""
    h, w = g.shape
    src, dst = [], []
    for n in NERI:
        uc = u_nero(n)
        vs = np.linspace(0.45, LB - 0.35, 9)
        pts = proietta(H, [(uc, v) for v in vs])
        if not any(_dentro(p, w, h) for p in pts):
            continue
        sc = _scala_px(H, uc, LB / 2)
        for v, (x, y) in zip(vs, pts):
            if not (8 < y < h - 8 and 0 <= x < w):
                continue
            yi = int(round(y))
            lo, hi = int(max(0, x - 0.7 * sc)), int(min(w, x + 0.7 * sc))
            if hi - lo < 4:
                continue
            for a, b in _runs(g[yi, lo:hi] < T):
                if 0.45 * BW * sc <= (b - a) <= 1.35 * BW * sc * 1.25:
                    xc = lo + (a + b) / 2.0
                    if abs(xc - x) < 0.40 * sc:
                        src.append((uc, v)); dst.append((xc, y))
                        break
        # fondo del nero: scendo lungo l'asse finche' diventa chiaro
        p0 = proietta(H, [(uc, LB - 1.0)])[0]
        p1 = proietta(H, [(uc, LB + 1.2)])[0]
        L = int(np.linalg.norm(p1 - p0))
        if L < 5:
            continue
        ts = np.linspace(0, 1, L)
        xs = (p0[0] + ts * (p1[0] - p0[0])).round().astype(int)
        ys = (p0[1] + ts * (p1[1] - p0[1])).round().astype(int)
        ok = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        if ok.sum() < L * 0.9:
            continue
        xs, ys = np.clip(xs, 0, w - 1), np.clip(ys, 0, h - 1)
        prof = g[ys, xs]
        buio = prof < T
        if buio[:max(3, L // 6)].mean() < 0.8:       # non parte dentro il nero (mano / sfocato)
            continue
        k = int(np.argmax(~buio & (np.convolve(~buio, np.ones(3), "same") >= 3)))
        if k > 0:
            xe, ye = xs[k] + 0.0, ys[k] + 0.0
            # centro orizzontale del nero a quella quota
            row = g[int(ye) - 3, max(0, int(xe - sc)):min(w, int(xe + sc))] < T
            rr = _runs(row)
            if rr:
                a, b = min(rr, key=lambda r: abs((r[0] + r[1]) / 2 + max(0, int(xe - sc)) - xe))
                if 0.45 * BW * sc <= (b - a) <= 1.6 * BW * sc:
                    xe = max(0, int(xe - sc)) + (a + b) / 2.0
            src.append((uc, LB)); dst.append((xe, ye - 1.5))
    # feltro rosso = bordo posteriore (vincola solo v)
    if red is not None:
        us = np.arange(-9, 10, 0.5)
        for u in us:
            x, y = proietta(H, [(u, V_FELTRO)])[0]
            if not (0 <= x < w and 12 < y < h - 12):
                continue
            sc = _scala_px(H, u, 0)
            xi = int(x)
            lo, hi = int(max(0, y - 0.4 * sc)), int(min(h, y + 0.4 * sc))
            col = red[lo:hi, max(0, xi - 1):xi + 2].mean(axis=1) > 40
            if col.sum() >= 3:
                yy = lo + np.where(col)[0].mean()
                src.append((u, V_FELTRO)); dst.append((x, yy))
    return np.float32(src), np.float32(dst)


def affina(g, H, red, iters=3):
    T = _soglia(g)
    n_in = 0
    for _ in range(iters):
        s, d = misure(g, H, T, red)
        if len(s) < 12:
            break
        H2, m = cv2.findHomography(s, d, cv2.RANSAC, 3.0)
        if H2 is None or m.sum() < 10:
            break
        H, n_in = H2, int(m.sum())
    return H, n_in


def maschera_tastiera(H, shape):
    h, w = shape
    poly = proietta(H, [(-12, 0), (12, 0), (12, LW), (-12, LW)])
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.int32(poly)], 255)
    return m


def flusso(prev, cur, H_prev):
    m = maschera_tastiera(H_prev, prev.shape)
    p0 = cv2.goodFeaturesToTrack(prev, 400, 0.01, 6, mask=m)
    if p0 is None or len(p0) < 12:
        return np.eye(3)
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, p0, None, winSize=(31, 31), maxLevel=4)
    ok = st.ravel() == 1
    if ok.sum() < 12:
        return np.eye(3)
    Hf, mm = cv2.findHomography(p0[ok], p1[ok], cv2.RANSAC, 3.0)
    return Hf if Hf is not None else np.eye(3)


def rosso(frame):
    b, g, r = [frame[..., i].astype(np.int16) for i in range(3)]
    return (r - (g + b) // 2).astype(np.int16)


# ------------------------------------------------- ancoraggio dal profilo dei tasti
# Il passo si misura confrontando il profilo di colonne scure (i tasti neri su fondo
# bianco) con la maschera del modello (neri + bianchi): il confronto e' sensibile alla
# SCALA, quindi sceglie l'ottava di passo giusta. I centri dei run invece si incatenano
# anche a passi sbagliati (meta' o doppio), per questo il filtro sulle larghezze dei
# run da solo non basta quando la tastiera e' lontana (neri piu' stretti di 1.5% di w).

_RES_LUT = 0.02        # risoluzione della maschera attesa (in larghezze di bianco)
_LARG_BANDA = 0.14     # altezza della banda di righe del profilo (frazione di h)


def _lut_attesa():
    """Maschera attesa su u in [0, 7) (1 = tasto nero), centrata e normalizzata."""
    u = np.arange(0.0, 7.0, _RES_LUT)
    m = np.zeros(u.size)
    for n in NERI[:5]:                              # un'ottava completa di neri
        o = u_nero(n) % 7.0
        m[np.abs(((u - o + 3.5) % 7.0) - 3.5) < BW / 2.0] = 1.0
    return m - m.mean()


_LUT_ATTESA = _lut_attesa()
_LUT_SCARTO = float(_LUT_ATTESA.std())


def _ncc_profilo(prof, s, fasi):
    """Correlazione (NCC) fra profilo di colonne e maschera attesa, per ogni fase."""
    out = np.zeros(fasi.size)
    p = prof - prof.mean()
    np_ = float(np.linalg.norm(p))
    if np_ < 1e-9 or s < 2.0:
        return out
    # il profilo ha una riga per colonna: la maschera campionata ha scarto ~ quello della
    # tavola, quindi il denominatore e' |p| * sqrt(n_colonne) * scarto
    den = np_ * np.sqrt(prof.size) * _LUT_SCARTO
    if den < 1e-9:
        return out
    iu = np.arange(prof.size, dtype=np.float64) / s
    for k, f0 in enumerate(fasi):
        idx = np.rint((iu - f0) % 7.0 / _RES_LUT).astype(np.int64) % _LUT_ATTESA.size
        out[k] = float(p @ _LUT_ATTESA[idx]) / den
    return out


def _bande_righe(g, T, w, h):
    """Bande di righe candidate per il profilo (dove ci sono tasti neri)."""
    wmin = max(3, int(0.008 * w))
    wmax = max(6, int(0.075 * w))
    ys = [y for y in range(max(3, int(0.04 * h)), int(0.88 * h))
          if sum(1 for a, b in _runs(g[y] < T) if wmin <= b - a <= wmax) >= 5]
    if not ys:
        return []
    blocchi, cur = [], [ys[0]]
    for y in ys[1:]:
        if y - cur[-1] <= 6:
            cur.append(y)
        else:
            blocchi.append(cur); cur = [y]
    blocchi.append(cur)
    blocchi.sort(key=len, reverse=True)
    alt = max(6, int(_LARG_BANDA * h))
    bande = []
    for b in blocchi[:2]:
        b0, b1 = b[0], b[-1]
        for q in (0.0, 0.25, 0.5, 0.75):
            ya = int(b0 + q * max(0, b1 - b0))
            if ya + 6 <= min(h, ya + alt):
                bande.append((ya, min(h, ya + alt)))
    return bande


def _cerca_profilo(prof, s_lo, s_hi, passo_s, passo_f):
    """Miglior (s, fase, ncc) sul profilo dato."""
    mig = None
    s = s_lo
    while s <= s_hi:
        fasi = np.arange(0.0, 7.0, passo_f)
        v = _ncc_profilo(prof, s, fasi)
        j = int(np.argmax(v))
        if mig is None or v[j] > mig[2]:
            mig = (float(s), float(fasi[j]), float(v[j]))
        s += passo_s
    return mig


def passo_profilo(frame):
    """
    Passo dei tasti (px per tasto bianco) dal profilo: (s, fase, ncc, ya, yb) o None.

    La fase e' in larghezze di bianco: il centro di un nero sta a `x = fase + s * u`.
    """
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    T = _soglia(g)
    s_lo, s_hi = w / 60.0, w / 10.0           # pianoforte reale: 52 bianchi al massimo
    mig = None
    for ya, yb in _bande_righe(g, T, w, h):
        prof = (g[ya:yb] < T).mean(axis=0)
        grosso = _cerca_profilo(prof, s_lo, s_hi, max(1.0, 0.04 * s_lo), 0.30)
        if grosso is None:
            continue
        fine = _cerca_profilo(prof, grosso[0] - 1.5, grosso[0] + 1.5, 0.15, 0.10)
        if fine is None:
            continue
        best = fine if fine[2] > grosso[2] else grosso
        if mig is None or best[2] > mig[2]:
            mig = (best[0], best[1], best[2], ya, yb)
    return mig


def H_profilo(frame, nota_gruppo2=61):
    """Omografia grezza dal profilo (affine, scala isotropa): passo, fase, quota."""
    p = passo_profilo(frame)
    if p is None:
        return None
    s, fase, _, _, _ = p
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    # ottava assoluta: il gruppo da DUE neri piu' vicino al centro e' [nota, nota+2]
    giu, su = u_nero(nota_gruppo2), u_nero(nota_gruppo2 + 2)
    base = 0.5 * (giu + su)
    k_ott = int(round(((w / 2.0 - fase) / s - base) / 7.0))
    fase += 7.0 * k_ott * s
    # bordo posteriore dei tasti: prima riga con neri (come H_iniziale classico)
    T = _soglia(g)
    wmin = max(3, int(0.008 * w))
    wmax = max(6, int(0.075 * w))
    ys = [y for y in range(max(3, int(0.04 * h)), int(0.88 * h))
          if sum(1 for a, b in _runs(g[y] < T) if wmin <= b - a <= wmax) >= 5]
    if not ys:
        return None
    y_back = float(ys[0])
    # scala verticale: distanza fra bordo posteriore e punte dei neri (LB in bianchi)
    xs = []
    for n in NERI[:5]:
        o = u_nero(n) % 7.0
        for k in range(-2, int(w / (7.0 * s)) + 3):
            x = fase + s * (o + 7.0 * k)
            if 2.0 <= x < w - 2.0:
                xs.append(x)
    s_y = s
    if len(xs) >= 6:
        osc = (g[:, np.rint(xs).astype(int)] < T).mean(axis=1)
        i0 = int(min(h - 1, max(0, y_back)))
        i1 = int(min(h - 1, y_back + (LB + 2.0) * s))
        sotto = i0 + int(np.argmax(osc[i0:i1 + 1] < 0.55))     # punte dei neri
        if i0 < sotto < i1 and osc[i0:sotto].mean() > 0.6:
            misura = (sotto - y_back) / LB
            if 0.5 * s <= misura <= 1.6 * s:
                s_y = misura
    return np.float64([[s, 0.0, fase], [0.0, s_y, y_back], [0.0, 0.0, 1.0]])


def _H_iniziale_classico(frame, nota_gruppo2=61):
    """
    Frame 0, automatico: neri a due quote -> gruppi 2/3 dal passo -> omografia grezza.
    `nota_gruppo2` = nota del primo nero del gruppo da DUE neri piu' vicino al centro
    (C#4 = 61 di default). Lo schema 2/3 fissa la nota entro l'ottava, non l'ottava.
    """
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    T = _soglia(g)
    lo, hi = 0.015 * w, 0.075 * w

    def neri_riga(y):
        return [((a + b) / 2.0, b - a) for a, b in _runs(g[y] < T) if lo <= b - a <= hi]

    ys = [y for y in range(int(0.15 * h), int(0.85 * h)) if len(neri_riga(y)) >= 5]
    if not ys:
        raise RuntimeError("tasti neri non trovati sul primo frame")
    blocchi, cur = [], [ys[0]]
    for y in ys[1:]:                              # blocco piu' lungo di righe con >=5 neri
        if y - cur[-1] <= 4:
            cur.append(y)
        else:
            blocchi.append(cur); cur = [y]
    blocchi.append(cur)
    ys = max(blocchi, key=len)
    ya = ys[0] + 25
    yb = ys[0] + int(0.55 * (ys[-1] - ys[0]))
    ra = [c for c, _ in neri_riga(ya)]
    rb = [c for c, _ in neri_riga(yb)]
    if len(ra) < 5 or len(rb) < 5:
        raise RuntimeError("neri insufficienti sul primo frame")
    rb_ok, ra_ok = [], []                         # accoppio per vicinanza (un nero puo' mancare in una riga)
    for c in ra:
        d = [abs(c - x) for x in rb]
        j = int(np.argmin(d))
        if d[j] < 0.12 * w:
            ra_ok.append(c); rb_ok.append(rb[j])
    if len(ra_ok) < 5:
        raise RuntimeError("neri incoerenti fra le due quote del primo frame")
    ra, rb = ra_ok, rb_ok
    sp = np.diff(ra)
    piccolo = float(np.median(sp[sp < 1.4 * sp.min()]))
    wpx = piccolo / 1.15
    grande = sp > 1.4 * sp.min()
    # gruppi separati dai passi grandi
    gruppi, cur = [], [0]
    for i, gr in enumerate(grande):
        if gr:
            gruppi.append(cur); cur = [i + 1]
        else:
            cur.append(i + 1)
    gruppi.append(cur)
    due = [k for k, gp in enumerate(gruppi) if len(gp) == 2]
    if not due:
        raise RuntimeError("nessun gruppo da 2 neri completo sul primo frame")
    k2 = min(due, key=lambda k: abs(np.mean([ra[i] for i in gruppi[k]]) - w / 2))
    # assegno le note: C# D# | F# G# A# | C# D# | ...
    seq = [1, 3, 6, 8, 10]
    note = {}
    i0 = gruppi[k2][0]
    pc0 = nota_gruppo2
    k = 0
    pos = 0
    # indice assoluto nella sequenza dei neri (da nota_gruppo2 avanti e indietro)
    ordine = [n for n in range(NOTA_MIN, NOTA_MAX + 1) if e_nero(n)]
    j0 = ordine.index(nota_gruppo2)
    for i in range(len(ra)):
        note[i] = ordine[j0 + (i - i0)]
    src, dst = [], []
    for i in range(len(ra)):
        u = u_nero(note[i])
        src += [(u, (ya - ys[0]) / wpx), (u, (yb - ys[0]) / wpx)]
        dst += [(ra[i], ya), (rb[i], yb)]
    H, _ = cv2.findHomography(np.float32(src), np.float32(dst), cv2.RANSAC, 4.0)
    if H is None:
        raise RuntimeError("omografia iniziale non calcolabile")
    return H


def H_iniziale(frame, nota_gruppo2=61):
    """
    Griglia iniziale senza storia: prova l'ancoraggio dal profilo (passo certo anche
    quando la tastiera e' lontana) e quello classico, poi tiene il migliore.

    Il confronto si fa sugli inlier di `affina` sul frame: una griglia sbagliata
    aggancia pochi tasti veri, una giusta ne aggancia decine.
    """
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    red = rosso(frame)
    cand: list[tuple[np.ndarray, int]] = []
    try:
        Hp = H_profilo(frame, nota_gruppo2)
    except (RuntimeError, ValueError):
        Hp = None
    if Hp is not None:
        H2, k2 = affina(g, Hp, red, 3)
        cand.append((np.float64(H2), int(k2)) if k2 >= 10 else (np.float64(Hp), int(k2)))
    try:
        Hc = np.float64(_H_iniziale_classico(frame, nota_gruppo2))
        H3, k3 = affina(g, Hc, red, 3)
        cand.append((np.float64(H3), int(k3)) if k3 >= 10 else (np.float64(Hc), int(k3)))
    except (RuntimeError, ValueError):
        pass
    if not cand:
        raise RuntimeError("griglia iniziale non calcolabile")
    return max(cand, key=lambda c: c[1])[0]


def _disegna(f, H, etichette=True):
    o = f.copy()
    for n in BIANCHI:
        cv2.polylines(o, [np.int32(poligono_tasto(H, n))], True, (60, 220, 60), 2, cv2.LINE_AA)
    for n in NERI:
        cv2.polylines(o, [np.int32(poligono_tasto(H, n))], True, (255, 160, 30), 2, cv2.LINE_AA)
    if etichette:
        h, w = f.shape[:2]
        for n in BIANCHI:
            p = poligono_tasto(H, n)
            x, y = (p[2] + p[3]) / 2
            if 0 < x < w - 14 and 0 < y < h - 4:
                t = nome(n)
                pos = (int(x) - 8 * len(t) // 2 - 3, int(y) - 10)
                cv2.putText(o, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(o, t, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return o


def _celle(H, n, k=3):
    """k celle lungo la profondita' del tasto (punta/centro/base): poligoni nel frame."""
    if e_nero(n):
        uc, a, b, L = u_nero(n), u_nero(n) - BW / 2, u_nero(n) + BW / 2, LB
    else:
        a = u_bianco(n); b = a + 1; L = LW
        if (n + 1) <= NOTA_MAX and e_nero(n + 1):      # a destra c'e' un nero: lascio il tasto intero
            pass
    out = []
    for j in range(k):
        v0, v1 = L * j / k, L * (j + 1) / k
        out.append(proietta(H, [(a, v0), (b, v0), (b, v1), (a, v1)]))
    return out


def main(argv=None):
    import argparse, json, time
    from pathlib import Path
    p = argparse.ArgumentParser(description="Griglia prospettica dei tasti, frame per frame.")
    p.add_argument("video")
    p.add_argument("-o", "--output", default="out_griglia")
    p.add_argument("--nota-gruppo2", type=int, default=61,
                   help="nota del primo nero del gruppo da 2 neri piu' vicino al centro (61=C#4)")
    p.add_argument("--senza-json", action="store_true")
    a = p.parse_args(argv)
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened():
        raise SystemExit(f"impossibile aprire {a.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W, Hh = int(cap.get(3)), int(cap.get(4))
    # H.264 (`avc1`) e' l'unico mp4 che i browser riproducono: se questo build di OpenCV non
    # ha un encoder H.264 si ripiega su mp4v (MPEG-4 Part 2), leggibile fuori dal browser.
    vw = cv2.VideoWriter(str(out / "griglia.mp4"), cv2.VideoWriter_fourcc(*"avc1"), fps, (W, Hh))
    if not vw.isOpened():
        vw = cv2.VideoWriter(str(out / "griglia.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (W, Hh))
    H, prev, i, doc = None, None, 0, []
    t0 = time.time()
    while True:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if H is None:
            H = H_iniziale(f, a.nota_gruppo2)
            Hp = H
        else:
            diff = float(np.mean(np.abs(prev.astype(np.int16) - g.astype(np.int16))))
            if diff < _SOGLIA_FERMO:              # immagine identica: geometria invariata
                Hp = H
            elif diff >= _SOGLIA_TAGLIO:          # cambio di inquadratura: griglia da zero
                try:
                    H = H_iniziale(f, a.nota_gruppo2)
                except (RuntimeError, ValueError):
                    pass
                Hp = H
            else:
                Hp = flusso(prev, g, H) @ H
        H2, k = affina(g, Hp, rosso(f), 3)
        H = H2 if k >= 10 else Hp
        prev = g
        vw.write(_disegna(f, H))
        if i == 0:
            cv2.imwrite(str(out / "primo_frame_griglia.jpg"), _disegna(f, H))
        if not a.senza_json:
            tasti = {}
            for n in BIANCHI + NERI:
                pol = poligono_tasto(H, n)
                if not (np.isfinite(pol).all() and (pol[:, 0] > -50).any() and (pol[:, 0] < W + 50).any()):
                    continue
                if pol[:, 0].max() < 0 or pol[:, 0].min() > W:
                    continue
                tasti[str(n)] = {"nome": nome(n), "nero": e_nero(n),
                                 "poligono": np.round(pol, 1).tolist(),
                                 "celle_profondita": [np.round(c, 1).tolist() for c in _celle(H, n)]}
            doc.append({"frame": i, "t": round(i / fps, 4), "inlier": k,
                        "H": np.round(H, 6).tolist(), "tasti": tasti})
        i += 1
    cap.release(); vw.release()
    if not a.senza_json:
        (out / "griglia.json").write_text(json.dumps(
            {"video": Path(a.video).name, "fps": fps, "n_frame": i,
             "modello": {"LB": LB, "LW": LW, "BW": BW, "u0": "bordo sinistro di C4"},
             "frames": doc}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"{i} frame in {time.time() - t0:.1f} s -> {out}/")


if __name__ == "__main__":
    main()

````

---

_Fine del file._
