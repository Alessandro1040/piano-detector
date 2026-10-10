# Esito della prova del fix (2° giro)

> **Cosa contiene questa cartella (chiarimento).**
> I due moduli esistono qui in **due versioni**, per confronto:
> | file | md5 | cos'è |
> |---|---|---|
> | `0_prepara_VECCHIO.py` | `cb983fbf…` | il codice che **aveva** il difetto (quello dello screenshot) |
> | `griglia_prospettica_VECCHIO.py` | `8605de96…` | idem |
> | `0_prepara_NUOVO.py` | `5f4288e4…` | il fix **che mi hai mandato**, provato qui sotto |
> | `griglia_prospettica_NUOVO.py` | `bc9a3f22…` | idem |
>
> I due `_NUOVO` sono **byte-identici** (`md5 -r`) a quelli che ho messo in
> `addestra_tasti/0_prepara.py` e `griglia_prospettica.py` nel progetto: nessun'altra copia dei due
> moduli esiste nel repo (niente `*.pyc` stantii: il bytecode rigenerato dal run contiene il codice
> nuovo, es. la firma `_disegna(f, H, etichette=True, poligoni=None)`).

Applicati i due file nuovi (md5: `0_prepara.py` = `5f4288e4…`, `griglia_prospettica.py` = `bc9a3f22…`)
e rilanciato **lo stesso comando** di prima:

```
.venv-mp10/bin/python addestra_tasti/0_prepara.py \
  --video web_runs/_prepara/bf185370fd564edb/2024-02-15_22-18-32.mp4 \
  --out   web_runs/_prepara/bf185370fd564edb \
  --nome  2024-02-15_22-18-32_preparato
```

Esito: `EXIT=0`, ma il verdetto finale è **`incerto`**.

## 1. Quello che il fix ha risolto (misurato, stesso video)

| numero | prima (58 riavvii) | adesso |
|---|---|---|
| riavvii | 58 | **1** |
| riancorate | 0 | 0 |
| fotogrammi respinti dai freni | 2 | 0 |
| agganciati | 1800/1800 | 1799/1800 |
| deriva ai checkpoint | 0.0 → 0.8 tasti (cresceva) | **0.0 tasti, costante** |
| inlier mediano | 224 | 208 |

La deriva è sparita: la griglia non insegue più se stessa di fotogramma in fotogramma. Il
fotogramma 0 del video preparato è identico a prima (come promesso: `Ms[0]` = identità).
I 58 "riavvii" sono diventati 1 (un solo fotogramma perso e ritrovato).

## 2. Controllo indipendente della griglia in movimento

Il `*_griglia.mp4` è il fotogramma intero scalato a 1280x720 (2/3) con la griglia sopra. In quello
spazio, per ogni istante, si sono confrontati i **bordi delle righe blu** con i **tasti neri veri**:

| t | scarto orizzontale (mediano) |
|---|---|
| 0 | 0.0 px |
| 5-55 s | 0.0 ÷ 0.5 px |

72-73 linee blu trovate = **36 tasti neri × 2 lati**: un riquadro per tasto, tutti presenti.

In verticale il bordo basso del riquadro sta ~3-4 px (scala 2/3, ≈5 px reali) sotto la fine della
colonna scura, e lo stesso scarto c'è **anche a t=0**: è un offset ereditato dalla griglia del
fotogramma 0, **costante** su tutto il pezzo, non un errore dell'inseguimento.

Sul video *vecchio* invece a t=40 e t=45 risultava **una sola** linea blu (la griglia lì spariva) e
lo scarto massimo arrivava a 49 px: l'inseguimento nuovo è visibilmente più stabile.

## 3. Il verdetto "incerto" è un falso allarme di `verifica_griglia`

Separando le due assi (stessa misura della `verifica_griglia`, solo dx e dy stampate a parte),
sui 60 campioni:

```
|dx| mediano 0.0   max 1 px     buoni (<= 4 px)  60/60
|dy| mediano 12.0  max 12 px    buoni (<= 4 px)   4/60
```

La `dx` è perfetta. La `dy` è **saturata sul bordo della finestra di ricerca**: la ricerca in y è
limitata a `±min(cerca, 12)` e il massimo cade sempre lì. Le curve di concordanza in y non hanno un
picco, sono monotone:

```
  i= 420   s(0,0)=0.442 | y: -12:0.467 -6:0.460 0:0.442 +6:0.416 +12:0.387
  i=1020   s(0,0)=0.373 | y: -12:0.406 -6:0.395 0:0.373 +6:0.348 +12:0.321
```

Prova che non c'entra né `Ms` né la griglia: rifacendo la stessa misura **grezza** (fotogramma 0
contro fotogramma i, **senza nessuna compensazione del moto**), il profilo in y resta monotono
verso -12 per tutti i fotogrammi da 120 in poi, mentre il profilo in x ha il picco netto in 0:

```
  i= 420   y(-12,-6,0,6,12) = 0.467 0.460 0.442 0.416 0.387   picco_y = -12
           x(-20,-10,0,10,20) = 0.160 0.241 0.442 0.230 0.153  picco_x =  0
  i=1770   y(-12,-6,0,6,12) = 0.371 0.357 0.337 0.320 0.295   picco_y = -12
           x(-20,-10,0,10,20) = 0.154 0.226 0.337 0.220 0.149  picco_x =  0
```

Cioè: **la y del ritaglio è una direzione non discriminante su questa ripresa** (il ritaglio è
quasi tutto colonne verticali; sotto la tastiera c'è il corpo del pianista, fuori dal piano), e la
deriva monotona viene dal contenuto, non dal moto. Con `scarto = max(|dx|, |dy|)` una `dy`
saturata boccia **tutti** i campioni: 4/60 = solo il campione i=0, che è il riferimento contro se
stesso.

### Cosa servirebbe (per il prossimo giro)
- Usare la `x` come asse di misura (i tasti neri **non** si ripetono con periodo di un tasto: lì
  c'è il picco netto) e chiedere alla `y` un **picco vero**, non "il massimo > s0 + 0.004":
  se il massimo cade sul bordo della finestra la misura va dichiarata **non attendibile**, non
  "griglia staccata".
- In alternativa allargare la finestra in y e pretendere che il valore al picco superi quello ai
  due bordi (gobba, non rampa).
- Soglia "buono" a parte per asse, non `max(|dx|,|dy|)`.

## 4. Resta da sistemare (a monte, invariato)

Il verdetto statico del fotogramma 0 non è cambiato: `ok: inlier 231, plausibilità 0.90` con
**3 tasti neri fuori posto** (A#5, F#6, G#6) e 2 coperti. È la misura di partenza, non
l'inseguimento, esattamente come dicevi.

## File di confronto in questa cartella
- `controllo_nuovo_run_10-21.jpg` — immagine di controllo del run nuovo
- `CONFRONTO_nuovo_vs_vecchio_t0_t30.jpg` — t=0 e t=30, nuovo sopra / vecchio a confronto
- `ZOOM_nuovo_vs_vecchio_t29.jpg` — zoom (3x) sulla stessa zona a t=29, nuovo vs vecchio
- i video: `web_runs/_prepara/bf185370fd564edb/2024-02-15_22-18-32_preparato{,_griglia}.mp4`
  (i vecchi, per confronto, sono stati copiati in `/tmp/prima/`)
