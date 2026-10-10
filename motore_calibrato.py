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
        self._filtra_eventi()       # gancio dei sottotipi (prospettica: filtro mani)
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

    def _filtra_eventi(self) -> None:
        """Gancio di estensione: scarta eventi prima che vengano scritti (default: niente).

        Si chiama fra il calcolo degli eventi e la scrittura di notes.json / song.mid /
        griglia.mp4: quello che si vede, quello che si sente e il MIDI restano la stessa
        cosa. Il motore prospettico lo usa per il filtro mani.
        """
        return

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
