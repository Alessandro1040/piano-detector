"""
Sito web per scorrere un video frame by frame e vedere il pianoforte rilevato.

Il browser mostra il video (canvas), manda al server il singolo frame e riceve
le coordinate delle rilevazioni: nessuna conversione video lato server, quindi
funziona con *qualsiasi* formato che il browser sappia riprodurre.

Avvio:  python video_app.py
Apri:   http://127.0.0.1:7861
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory

from piano_detector import PianoDetector

BASE = Path(__file__).resolve().parent

MODELLI = {
    "yolov8m (veloce)": "weights/yolov8m-oiv7.pt",
    "yolov8l (preciso)": "weights/yolov8l-oiv7.pt",
    "yolov8x (massimo)": "weights/yolov8x-oiv7.pt",
}
MODELLO_DEFAULT = "yolov8m (veloce)"

# torch non è thread-safe sulle stesse istanze modello: serializziamo l'inferenza
_lock = threading.Lock()
_cache: dict[str, PianoDetector] = {}


def get_detector(modello: str, conf: float) -> PianoDetector:
    """Detector riusato fra le richieste (il modello viene caricato una volta)."""
    nome = MODELLI.get(modello)
    if nome is None:
        raise KeyError(f"Modello sconosciuto: {modello}")
    if nome not in _cache:
        _cache[nome] = PianoDetector(str(BASE / nome), conf=conf)
    _cache[nome].conf = conf
    return _cache[nome]


def _box_json(box, scelto: bool) -> dict:
    return {
        "x1": box.x1, "y1": box.y1, "x2": box.x2, "y2": box.y2,
        "confidenza": box.confidenza, "classe": box.classe, "scelto": scelto,
    }


app = Flask(__name__, static_folder=None)


@app.get("/")
def index():
    return send_from_directory(BASE, "video_viewer.html")


@app.get("/favicon.ico")
def favicon():
    """La pagina usa un'icona inline: qui rispondiamo 'no content' per evitare 404."""
    return "", 204


@app.get("/modelli")
def modelli():
    """Elenco dei modelli disponibili (con indicazione di quelli già scaricati)."""
    return jsonify([{
        "nome": k,
        "pesi": v,
        "presente": (BASE / v).exists(),
    } for k, v in MODELLI.items()])


DEMO = [BASE / "demo_video.webm", BASE / "demo_video.mp4"]


@app.get("/video-demo")
def video_demo():
    """Video di prova incluso nel progetto (se presente)."""
    for p in DEMO:
        if p.exists():
            return send_from_directory(BASE, p.name)
    return jsonify({"errore": "nessun video demo nel progetto"}), 404



@app.post("/detect")
def detect():
    """
    Input (multipart): frame=<jpeg/png>, conf, margine, modello.
    Output JSON: riquadri in pixel del frame originale + quale è quello scelto.
    """
    modello = request.form.get("modello", MODELLO_DEFAULT)
    conf = float(request.form.get("conf", 0.15))
    margine = float(request.form.get("margine", 0.0))

    file = request.files.get("frame")
    if file is None:
        return jsonify({"errore": "campo 'frame' mancante"}), 400
    buf = np.frombuffer(file.read(), np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"errore": "frame non decodificabile"}), 400

    try:
        det = get_detector(modello, conf)
    except KeyError as e:
        return jsonify({"errore": str(e)}), 400

    h, w = img.shape[:2]
    t0 = time.perf_counter()
    # una sola inferenza: detect_all; poi replichiamo la scelta di detect_piano
    with _lock:
        dets = det.detect_all(img)
    ms = (time.perf_counter() - t0) * 1000.0

    if not dets:
        return jsonify({"w": w, "h": h, "ms": ms, "boxes": [], "scelto": None})

    piani = [d for d in dets if d.classe == "piano"]
    best = piani[0] if piani else dets[0]
    best_coord = (best.x1, best.y1, best.x2, best.y2)
    scelto = det._espandi(best, img, margine) if margine > 0 else best

    return jsonify({
        "w": w, "h": h, "ms": ms,
        "boxes": [_box_json(d, (d.x1, d.y1, d.x2, d.y2) == best_coord) for d in dets],
        "scelto": _box_json(scelto, True),
    })


if __name__ == "__main__":
    print("🎹 Piano Detector — video viewer")
    print("   Apri  http://127.0.0.1:7861")
    app.run(host="127.0.0.1", port=7861, threaded=True, debug=False)
