#!/usr/bin/env python3
"""Ponte fra PPAN e lo Studio: porta l'output di `ppan_infer.py` nello **stesso schema**
della pipeline, piu' un'immagine del ritaglio che PPAN ha davvero usato.

Uso:
    python ppan_bridge.py notes_ppan.json notes.json video.mp4 prima_griglia.jpg

Perche' serve: lo Studio legge sempre `out/notes.json` e `out/prima_griglia.jpg`,
qualunque sia il motore. Convertendo qui, la tabella degli eventi, le statistiche,
il player MIDI e gli endpoint di download funzionano identici con PPAN e con la
pipeline, senza che il server debba sapere nulla di PPAN.

Gira nell'interprete di PPAN (serve cv2 + numpy) e non importa torch.
"""
from __future__ import annotations

import json
import pathlib
import sys

import cv2
import numpy as np

CROP_W, CROP_H = 720, 122          # geometria che il modello si aspetta
FPS_DEFAULT = 30.0

NOMI = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def nome_nota(midi: int) -> str:
    return "%s%d" % (NOMI[int(midi) % 12], int(midi) // 12 - 1)


def carica(percorso: pathlib.Path) -> dict:
    """Legge il JSON di PPAN (`{"notes": [...], "meta": {...}}`)."""
    return json.loads(pathlib.Path(percorso).read_text(encoding="utf-8"))


def eventi_da_note(note: list[dict], fps: float) -> list[dict]:
    """{note,start,duration,velocity} (PPAN) -> schema eventi della pipeline."""
    eventi = []
    for n in sorted(note, key=lambda x: float(x.get("start", 0.0))):
        onset = float(n.get("start", 0.0))
        durata = float(n.get("duration", 0.0))
        eventi.append({
            "nota": int(n["note"]),
            "nome": nome_nota(n["note"]),
            "onset": round(onset, 3),
            "offset": round(onset + durata, 3),
            "durata": round(durata, 3),
            "velocity": int(n.get("velocity", 80) or 80),
            "profondita": None,          # PPAN non stima la profondita' del tasto
            "mano": "",                  # PPAN non distingue la mano
            "frame_onset": int(round(onset * fps)),
            "frame_offset": int(round((onset + durata) * fps)),
        })
    return eventi


def riepilogo(eventi: list[dict], durata_s: float) -> dict:
    if not eventi:
        return {"n_eventi": 0, "note_uniche": 0, "note_al_secondo": 0.0,
                "durata_media": 0.0, "nota_piu_frequente": None, "intervallo_midi": None}
    note = [e["nota"] for e in eventi]
    conta: dict[int, int] = {}
    for n in note:
        conta[n] = conta.get(n, 0) + 1
    return {
        "n_eventi": len(eventi),
        "note_uniche": len(set(note)),
        "note_al_secondo": round(len(eventi) / durata_s, 3) if durata_s else 0.0,
        "durata_media": round(sum(e["durata"] for e in eventi) / len(eventi), 3),
        "nota_piu_frequente": max(conta, key=lambda k: conta[k]),
        "intervallo_midi": [min(note), max(note)],
    }


def proprieta_video(video: pathlib.Path) -> dict:
    cap = cv2.VideoCapture(str(video))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or FPS_DEFAULT)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()
    return {"fps": fps if fps > 0 else FPS_DEFAULT, "frame_totali": n,
            "larghezza": w, "altezza": h}


def frame_a(video: pathlib.Path, secondi: float) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(video))
    try:
        if secondi > 0:
            cap.set(cv2.CAP_PROP_POS_MSEC, secondi * 1000.0)
        ok, frame = cap.read()
        if not ok:                       # alcuni codec: meglio partire da zero
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


# ---------------------------------------------------------------- immagine
def ritaglia(frame: np.ndarray, meta: dict) -> np.ndarray | None:
    """La striscia 720x122 che il modello ha visto davvero (per l'anteprima).

    'quad' e 'bbox' dentro `meta` sono **quelli usati** da ppan_infer (gia'
    allargati all'aspetto 720:122), non quelli richiesti: l'anteprima e' fedele.
    """
    quad = meta.get("quad") or []
    bbox = meta.get("bbox") or []
    if len(quad) == 4:
        src = np.array([[float(x), float(y)] for x, y in quad], dtype=np.float32)
        dst = np.array([[0, 0], [CROP_W - 1, 0], [CROP_W - 1, CROP_H - 1], [0, CROP_H - 1]],
                       dtype=np.float32)
        return cv2.warpPerspective(frame, cv2.getPerspectiveTransform(src, dst), (CROP_W, CROP_H))
    if len(bbox) == 4:
        x1, y1, x2, y2 = [int(float(v)) for v in bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, min(x1, w - 1)), max(0, min(y1, h - 1))
        x2, y2 = max(x1 + 1, min(x2, w)), max(y1 + 1, min(y2, h))
        pezzo = frame[y1:y2, x1:x2]
        if pezzo.size:
            return cv2.resize(pezzo, (CROP_W, CROP_H))
    return None


def disegna(video: pathlib.Path, meta: dict, destinazione: pathlib.Path) -> bool:
    """Frame con la regione usata da PPAN + sotto la striscia raddrizzata."""
    frame = frame_a(video, float(meta.get("start_seconds") or 0.0))
    if frame is None:
        return False
    vis = frame.copy()
    quad = meta.get("quad") or []
    bbox = meta.get("bbox") or []
    if len(quad) == 4:
        punti = np.array([[int(round(float(x))), int(round(float(y)))] for x, y in quad],
                         dtype=np.int32)
        cv2.polylines(vis, [punti], True, (0, 235, 0), 2, cv2.LINE_AA)
        for etichetta, (x, y) in zip(("TL", "TR", "BR", "BL"), punti):
            cv2.circle(vis, (int(x), int(y)), 5, (0, 255, 255), -1, cv2.LINE_AA)
            cv2.putText(vis, etichetta, (int(x) + 7, int(y) - 7), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (0, 255, 255), 1, cv2.LINE_AA)
    elif len(bbox) == 4:
        x1, y1, x2, y2 = [int(round(float(v))) for v in bbox]
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 235, 0), 2, cv2.LINE_AA)
    fonte = {"auto": "ritaglio automatico", "quad": "4 angoli scelti da te",
             "bbox": "riquadro scelto da te", "track": "tastiera inseguita"}.get(
        str(meta.get("crop_source")), str(meta.get("crop_source")))
    cv2.putText(vis, "PPAN - regione usata (%s)" % fonte, (12, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 235, 0), 2, cv2.LINE_AA)

    striscia = ritaglia(frame, meta)
    if striscia is not None:
        striscia = cv2.copyMakeBorder(striscia, 26, 4, 0, 0, cv2.BORDER_CONSTANT,
                                      value=(26, 26, 26))
        cv2.putText(striscia, "quello che vede la rete: %dx%d (88 tasti)" % (CROP_W, CROP_H),
                    (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (60, 220, 255), 1, cv2.LINE_AA)
        larghezza = vis.shape[1]
        scala = larghezza / float(CROP_W)
        striscia = cv2.resize(striscia, (larghezza, max(1, int(striscia.shape[0] * scala))))
        vis = np.vstack([vis, striscia])
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    return bool(cv2.imwrite(str(destinazione), vis, [int(cv2.IMWRITE_JPEG_QUALITY), 88]))


# -------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print(__doc__)
        return 2
    sorgente, destinazione = pathlib.Path(args[0]), pathlib.Path(args[1])
    video = pathlib.Path(args[2]) if len(args) > 2 else None
    immagine = pathlib.Path(args[3]) if len(args) > 3 else None

    doc = carica(sorgente)
    meta = doc.get("meta") or {}
    note = doc.get("notes") or []
    if video is not None and video.is_file():
        prop = proprieta_video(video)
    else:
        prop = {"fps": float(meta.get("source_fps") or FPS_DEFAULT),
                "frame_totali": int(meta.get("n_frames_30fps") or 0),
                "larghezza": 0, "altezza": 0}
    fps = prop["fps"] or FPS_DEFAULT
    eventi = eventi_da_note(note, fps)
    durata = float(meta.get("duration_seconds") or 0.0)
    if not durata and prop["frame_totali"]:
        durata = prop["frame_totali"] / fps

    tastiera = meta.get("keyboard") or {}
    estensione = None
    if tastiera.get("first_note") is not None and tastiera.get("n_keys"):
        estensione = {"prima_nota": int(tastiera["first_note"]),
                      "ultima_nota": int(tastiera["first_note"]) + int(tastiera["n_keys"]) - 1,
                      "n_tasti": int(tastiera["n_keys"])}
    risultato = {
        "video": video.name if video is not None else str(meta.get("video") or ""),
        "motore": "ppan",
        "fps": round(fps, 3),
        "frame_totali": prop["frame_totali"],
        "durata_s": round(durata, 3),
        "larghezza": prop["larghezza"],
        "altezza": prop["altezza"],
        "estensione_tastiera": estensione,
        "eventi": eventi,
        "riepilogo": riepilogo(eventi, durata),
        "ppan": {
            "device": meta.get("device"),
            "crop_source": meta.get("crop_source"),
            "crop_keys": meta.get("crop_keys"),
            "thresholds": meta.get("thresholds"),
            "start_seconds": meta.get("start_seconds"),
            "max_seconds": meta.get("max_seconds"),
            "n_frames_30fps": meta.get("n_frames_30fps"),
            "elapsed_seconds": meta.get("elapsed_seconds"),
            "n_notes_raw": meta.get("n_notes_raw"),
            "min_note_seconds": meta.get("min_note_seconds"),
            "weights": meta.get("weights"),
        },
    }
    destinazione.write_text(json.dumps(risultato, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print("ponte: %d eventi nota -> %s" % (len(eventi), destinazione))
    if immagine is not None and video is not None and video.is_file():
        try:
            if disegna(video, meta, immagine):
                print("ponte: immagine del ritaglio -> %s" % immagine)
            else:
                print("ponte: video non leggibile, niente immagine")
        except Exception as exc:                                   # noqa: BLE001
            print("ponte: immagine non riuscita (%s: %s)" % (type(exc).__name__, exc))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:                                       # noqa: BLE001
        print("ponte: ERRORE %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        raise SystemExit(1)
