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
