"""
Pipeline video -> MIDI (stadio 2): orchestratore da riga di comando.

    python pipeline.py video.mp4 -o out/ \
        --modello yolov8l --conf 0.15 --fps-max 30 \
        --tracker template --senza-mani --prima-nota 21 --n-ottave 7 \
        --debug-video --limite 200

Catena: KeyboardTracker (E1) -> KeyboardGrid (E3) ; HandTracker (E2) ->
RilevatoreNote (E4) -> to_midi (E5). Produce in `out/`:
    notes.json, song.mid, prima_griglia.jpg, debug.mp4 (solo con --debug-video)

Se --prima-nota / --n-ottave mancano l'estensione e' STIMATA da
KeyboardGrid.stima_estensione (il numero di tasti e' abbastanza affidabile,
l'ottava assoluta no: in caso di dubbio passare --prima-nota).

Nessun download a runtime: pesi YOLO e modello delle mani devono essere file
locali; se mancano si esce con un errore che indica dove trovarli.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from keyboard_grid import KeyboardGrid, Tasto
from keyboard_tracker import KeyboardTracker, Traccia
from note_events import EventoNota, RilevatoreNote
from to_midi import riepiloga, salva_json, salva_midi

QUI = Path(__file__).resolve().parent
URL_YOLO = ("https://github.com/ultralytics/assets/releases/download/v8.3.0/"
            "yolov8l-oiv7.pt")
COLORI_DITA = {4: (0, 165, 255), 8: (0, 255, 255), 12: (0, 255, 0),
               16: (255, 128, 0), 20: (255, 0, 255)}


def avviso(msg: str) -> None:
    print(f"[AVVISO] {msg}", file=sys.stderr)


# ------------------------------------------------------------- percorsi
def _cerca(candidati: list[Path]) -> Path | None:
    for c in candidati:
        if c.is_file():
            return c
    return None


def risolvi_pesi_yolo(modello: str) -> Path | None:
    nome = modello if modello.endswith(".pt") else f"weights/{modello}-oiv7.pt"
    return _cerca([Path(nome), QUI / nome, Path(modello), QUI / modello])


def risolvi_modello_mani(percorso: str) -> Path | None:
    return _cerca([Path(percorso), QUI / percorso])


# ------------------------------------------------------------- disegno
def _testo(img, s, x, y, scala, col=(255, 255, 255)):
    cv2.putText(img, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scala, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, s, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scala, col, 1, cv2.LINE_AA)


def disegna_griglia(frame: np.ndarray, traccia: Traccia, tasti: list[Tasto],
                    attive: set[int] | None = None) -> np.ndarray:
    """Disegna box, quadrilatero, tasti (neri pieni) e nomi delle note sul frame."""
    attive = attive or set()
    out = frame.copy()
    sovra = out.copy()
    bianchi = [t for t in tasti if not t.nero]
    neri = [t for t in tasti if t.nero]
    for t in tasti:
        if t.nota in attive:
            cv2.fillPoly(sovra, [np.int32(t.poligono)], (0, 0, 255))
    for t in neri:
        if t.nota not in attive:
            cv2.fillPoly(sovra, [np.int32(t.poligono)], (90, 40, 20))
    out = cv2.addWeighted(sovra, 0.45, out, 0.55, 0)

    for t in bianchi:
        cv2.polylines(out, [np.int32(t.poligono)], True, (60, 220, 60), 1, cv2.LINE_AA)
    for t in neri:
        cv2.polylines(out, [np.int32(t.poligono)], True, (255, 160, 40), 1, cv2.LINE_AA)
    cv2.rectangle(out, (traccia.x1, traccia.y1), (traccia.x2, traccia.y2), (255, 0, 255), 1)
    if traccia.quad:
        cv2.polylines(out, [np.int32(traccia.quad)], True, (0, 255, 255), 2, cv2.LINE_AA)

    if bianchi:
        p = bianchi[0].poligono
        larg = math.dist(p[0], p[1])
        scala = float(min(max(larg / 45.0, 0.3), 0.7))
        for t in bianchi:
            if larg < 24 and not t.nome.startswith("C"):
                continue   # tasti stretti: solo i Do, per restare leggibili
            xm = int((t.poligono[2][0] + t.poligono[3][0]) / 2)
            ym = int((t.poligono[2][1] + t.poligono[3][1]) / 2) - 6
            (tw, _), _ = cv2.getTextSize(t.nome, cv2.FONT_HERSHEY_SIMPLEX, scala, 1)
            _testo(out, t.nome, xm - tw // 2, ym, scala)
    return out


def disegna_debug(frame, traccia, tasti, mani, attive, frame_idx, t) -> np.ndarray:
    out = disegna_griglia(frame, traccia, tasti, set(attive))
    for m in mani:
        for i, (x, y) in enumerate(m.tutte):
            cv2.circle(out, (int(x), int(y)), 2, (200, 200, 200), -1, cv2.LINE_AA)
        for d, (x, y) in m.punte.items():
            cv2.circle(out, (int(x), int(y)), 6, COLORI_DITA.get(d, (255, 255, 255)), -1, cv2.LINE_AA)
        x0, y0 = m.tutte[0]
        _testo(out, m.mano, int(x0) - 20, int(y0) + 24, 0.5)
    _testo(out, f"frame {frame_idx}  t={t:.2f}s  origine={traccia.origine}", 10, 24, 0.6)
    return out


def _mani_vicine(mani, traccia: Traccia):
    """Il box serve solo a FILTRARE: tiene le mani con almeno una punta vicino alla tastiera."""
    mx, my = 0.25 * traccia.larghezza, 0.25 * traccia.altezza
    x1, y1, x2, y2 = traccia.x1 - mx, traccia.y1 - my, traccia.x2 + mx, traccia.y2 + my
    return [m for m in mani
            if any(x1 <= x <= x2 and y1 <= y <= y2 for x, y in m.punte.values())]


# ------------------------------------------------------- video di debug
class ScrittoreFfmpeg:
    """Scrive frame BGR grezzi in un H.264/yuv420p tramite ffmpeg (fps esplicito, niente mp4v)."""

    def __init__(self, path: Path, larghezza: int, altezza: int, fps: float) -> None:
        exe = shutil.which("ffmpeg") or ("/opt/homebrew/bin/ffmpeg"
                                         if Path("/opt/homebrew/bin/ffmpeg").exists() else None)
        if exe is None:
            raise RuntimeError("ffmpeg non trovato nel PATH (ne' in /opt/homebrew/bin)")
        self.larghezza, self.altezza = larghezza, altezza
        self.guasto = False
        cmd = [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{larghezza}x{altezza}", "-r", f"{fps:.6f}", "-i", "-",
               "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
               "-crf", "23", str(path)]
        self._p = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def scrivi(self, frame: np.ndarray) -> None:
        if self.guasto:
            return
        if frame.shape[1] != self.larghezza or frame.shape[0] != self.altezza:
            frame = cv2.resize(frame, (self.larghezza, self.altezza))
        try:
            self._p.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
        except (BrokenPipeError, OSError):
            self.guasto = True
            avviso("ffmpeg ha interrotto la scrittura di debug.mp4")

    def chiudi(self) -> None:
        try:
            self._p.stdin.close()
        except OSError:
            pass
        self._p.wait()


# ----------------------------------------------------------------- CLI
def costruisci_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pipeline video -> MIDI (stadio 2).")
    p.add_argument("video", help="file video di input (es. demo_video.mp4)")
    p.add_argument("-o", "--output", default="out", help="cartella di output")
    p.add_argument("--modello", default="yolov8l",
                   help="yolov8m | yolov8l | yolov8x oppure percorso di un .pt")
    p.add_argument("--conf", type=float, default=0.15, help="soglia di confidenza del detector")
    p.add_argument("--fps-max", type=float, default=30.0,
                   help="se il video ha piu' fps, si elabora 1 frame ogni N")
    p.add_argument("--tracker", choices=("template", "mil"), default="template")
    p.add_argument("--redetect", type=int, default=30,
                   help="intervallo (frame) di ri-rilevazione della tastiera")
    p.add_argument("--senza-mani", action="store_true", help="salta il rilevamento mani/note")
    p.add_argument("--pesi-mani", default="weights/hand_landmarker.task")
    p.add_argument("--prima-nota", type=int, default=None,
                   help="MIDI della prima nota visibile (default: stima automatica)")
    p.add_argument("--n-ottave", type=float, default=None,
                   help="ottave visibili (default: stima automatica)")
    p.add_argument("--ultima-nota", type=int, default=None,
                   help="alternativa a --n-ottave: MIDI dell'ultima nota visibile")
    p.add_argument("--senza-prospettiva", action="store_true",
                   help="griglia su rettangolo assi-allineato invece che su quadrilatero")
    p.add_argument("--debug-video", action="store_true", help="scrive debug.mp4 (via ffmpeg)")
    p.add_argument("--limite", type=int, default=None, help="elabora solo i primi N frame")
    return p


def crea_griglia(args, traccia: Traccia, larghezza_frame: int) -> KeyboardGrid:
    """Sceglie l'estensione (manuale o stimata) e crea la KeyboardGrid."""
    prospettiva = not args.senza_prospettiva
    stima = KeyboardGrid(prospettiva=prospettiva)
    s_prima, s_ultima = stima.stima_estensione(traccia, larghezza_frame)
    prima = args.prima_nota if args.prima_nota is not None else s_prima
    if args.n_ottave is not None:
        griglia = KeyboardGrid(prima_nota=prima, n_ottave=args.n_ottave, prospettiva=prospettiva)
    else:
        ultima = args.ultima_nota if args.ultima_nota is not None \
            else prima + (s_ultima - s_prima)
        griglia = KeyboardGrid(prima_nota=prima, ultima_nota=ultima, prospettiva=prospettiva)
    manuale = args.prima_nota is not None
    print(f"[griglia] estensione {griglia.prima_nota}..{griglia.ultima_nota} "
          f"({griglia.n_bianchi} bianchi) - "
          f"{'prima nota manuale' if manuale else 'STIMATA, verificare la prima nota'}; "
          f"stima: {stima.info_stima}")
    if not manuale:
        avviso("--prima-nota non indicata: l'ottava assoluta e' un'ipotesi (finestra centrata). "
               "Se le note risultano trasposte, rilancia con --prima-nota.")
    return griglia


def main(argv=None) -> int:
    args = costruisci_parser().parse_args(argv)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    pesi = risolvi_pesi_yolo(args.modello)
    if pesi is None:
        print(f"[ERRORE] Pesi YOLO non trovati per '{args.modello}'. Attesi in "
              f"weights/{args.modello}-oiv7.pt (oppure passa un percorso .pt con --modello).\n"
              f"Esempio di download manuale: {URL_YOLO}", file=sys.stderr)
        return 2

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        print(f"[ERRORE] impossibile aprire il video: {args.video}", file=sys.stderr)
        return 2
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if not math.isfinite(fps) or fps <= 0:
        avviso("fps non leggibili dal video: assumo 30")
        fps = 30.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_tot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    passo = max(1, int(math.ceil(fps / max(args.fps_max, 1e-6) - 1e-6)))
    print(f"[video] {args.video}: {W}x{H}, {fps:.3f} fps, {n_tot} frame, passo={passo}")

    from piano_detector import PianoDetector   # import qui: py_compile/--help non lo richiedono
    detector = PianoDetector(str(pesi), conf=args.conf)
    tracker = KeyboardTracker(detector, conf=args.conf, tracker=args.tracker,
                              intervallo_redetect=args.redetect,
                              raffina_quad=not args.senza_prospettiva)

    mani_tracker = None
    if not args.senza_mani:
        try:
            from hands import HandTracker
            modello_mani = risolvi_modello_mani(args.pesi_mani)
            mani_tracker = HandTracker(str(modello_mani or args.pesi_mani))
        except (ImportError, FileNotFoundError) as e:
            avviso(f"mani disattivate: {e}")
            mani_tracker = None
    rilevatore = RilevatoreNote(fps=fps) if mani_tracker is not None else None

    scrittore = None
    if args.debug_video:
        try:
            scrittore = ScrittoreFfmpeg(out_dir / "debug.mp4", W, H, fps / passo)
        except RuntimeError as e:
            avviso(f"debug.mp4 disattivato: {e}")

    eventi: list[EventoNota] = []
    griglia: KeyboardGrid | None = None
    ultima_traccia: Traccia | None = None
    tasti: list[Tasto] = []
    primo_frame = None
    prima_griglia_salvata = False
    n_elaborati = n_senza_traccia = n_mani_errori = 0
    n_frame_letti = 0

    try:
        idx = -1
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            idx += 1
            if args.limite is not None and idx >= args.limite:
                break
            n_frame_letti = idx + 1
            if primo_frame is None:
                primo_frame = frame.copy()
            if idx % passo != 0:
                continue
            n_elaborati += 1
            t = idx / fps

            traccia = tracker.update(frame, idx)
            if traccia is None:
                n_senza_traccia += 1
                traccia = ultima_traccia   # si riusa l'ultima nota valida (mai un box nuovo inventato)
            else:
                ultima_traccia = traccia
            if traccia is None:
                continue

            if griglia is None:
                griglia = crea_griglia(args, traccia, W)
            try:
                tasti = griglia.costruisci(traccia, frame.shape[:2])
            except ValueError as e:
                avviso(f"frame {idx}: griglia non costruibile ({e})")
                continue

            if not prima_griglia_salvata:
                cv2.imwrite(str(out_dir / "prima_griglia.jpg"),
                            disegna_griglia(frame, traccia, tasti))
                prima_griglia_salvata = True

            mani = []
            if mani_tracker is not None:
                try:
                    mani = _mani_vicine(
                        mani_tracker.processa(frame, int(round(idx * 1000.0 / fps))), traccia)
                except Exception as e:  # MediaPipe non deve far cadere la pipeline
                    n_mani_errori += 1
                    if n_mani_errori == 1:
                        avviso(f"errore nel rilevamento mani (frame {idx}): {e}")
                    mani = []
            if rilevatore is not None:
                eventi += rilevatore.aggiorna(idx, mani, griglia)

            if scrittore is not None:
                attive = rilevatore.note_attive() if rilevatore is not None else []
                scrittore.scrivi(disegna_debug(frame, traccia, tasti, mani, attive, idx, t))
    except KeyboardInterrupt:
        avviso("interrotto dall'utente: salvo i risultati parziali")
    finally:
        cap.release()
        if mani_tracker is not None:
            mani_tracker.chiudi()
        if scrittore is not None:
            scrittore.chiudi()

    if rilevatore is not None:
        eventi += rilevatore.chiudi()
    eventi.sort(key=lambda e: (e.onset, e.nota))

    if not prima_griglia_salvata and primo_frame is not None:
        img = primo_frame.copy()
        _testo(img, "TASTIERA NON RILEVATA", 20, 40, 1.0, (0, 0, 255))
        cv2.imwrite(str(out_dir / "prima_griglia.jpg"), img)
    if griglia is None:
        avviso("tastiera mai rilevata: prova ad abbassare --conf o a usare --modello yolov8x")
    if mani_tracker is None and not args.senza_mani:
        avviso("nessuna mano elaborata: notes.json sara' vuoto")
    if n_senza_traccia:
        avviso(f"{n_senza_traccia} frame senza traccia della tastiera (riusata l'ultima valida)")

    durata = (n_frame_letti / fps) if n_frame_letti else 0.0
    ext = ({"prima_nota": griglia.prima_nota, "ultima_nota": griglia.ultima_nota,
            "n_tasti": griglia.ultima_nota - griglia.prima_nota + 1}
           if griglia is not None else None)
    meta = {"video": Path(args.video).name, "fps": fps, "frame_totali": n_frame_letti,
            "durata_s": durata, "larghezza": W, "altezza": H, "estensione_tastiera": ext}
    salva_json(eventi, str(out_dir / "notes.json"), meta)
    salva_midi(eventi, str(out_dir / "song.mid"))

    r = riepiloga(eventi, durata)
    print("\n=== RIEPILOGO ===")
    print(f"frame letti/elaborati : {n_frame_letti}/{n_elaborati}")
    print(f"estensione tastiera   : {ext}")
    print(f"eventi nota           : {r['n_eventi']} (note uniche {r['note_uniche']})")
    print(f"note al secondo       : {r['note_al_secondo']}  durata media {r['durata_media']} s")
    print(f"nota piu' frequente   : {r['nota_piu_frequente']}  intervallo {r['intervallo_midi']}")
    print(f"output in             : {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
