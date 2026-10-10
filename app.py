"""
Interfaccia web del Piano Detector (Gradio).

Avvio:  python app.py
Poi apri http://127.0.0.1:7860 nel browser.
"""

import json
from dataclasses import asdict

import cv2
import gradio as gr

from piano_detector import PianoDetector

MODELLI = {
    "YOLOv8l (più preciso, consigliato)": "weights/yolov8l-oiv7.pt",
    "YOLOv8m (più veloce)": "weights/yolov8m-oiv7.pt",
}
_cache: dict[str, PianoDetector] = {}


def get_detector(nome: str, conf: float) -> PianoDetector:
    pesi = MODELLI[nome]
    if pesi not in _cache:
        _cache[pesi] = PianoDetector(pesi, conf=conf)
    _cache[pesi].conf = conf
    return _cache[pesi]


def analizza(image, nome_modello, conf, margine):
    if image is None:
        return None, None, "Carica un'immagine."
    img_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    det = get_detector(nome_modello, conf)

    annotata = det.annota(img_bgr, margine=margine / 100)
    box = det.detect_piano(img_bgr, margine=margine / 100)

    annotata_rgb = cv2.cvtColor(annotata, cv2.COLOR_BGR2RGB)
    if box is None:
        return annotata_rgb, None, "❌ Nessun pianoforte rilevato. Prova ad abbassare la soglia."

    crop_rgb = cv2.cvtColor(img_bgr[box.y1:box.y2, box.x1:box.x2], cv2.COLOR_BGR2RGB)
    info = {
        "riquadro": asdict(box),
        "dimensione_crop": f"{box.larghezza}x{box.altezza} px",
    }
    return annotata_rgb, crop_rgb, json.dumps(info, ensure_ascii=False, indent=2)


with gr.Blocks(title="Piano Detector") as demo:
    gr.Markdown("# 🎹 Piano Detector\n"
                "Carica un'immagine (o un frame video): trovo il riquadro del pianoforte "
                "e te lo restituisco ritagliato.")
    with gr.Row():
        with gr.Column():
            inp = gr.Image(label="Immagine di input")
            modello = gr.Dropdown(list(MODELLI), value=list(MODELLI)[0], label="Modello")
            conf = gr.Slider(0.02, 0.8, value=0.15, step=0.01,
                             label="Soglia di confidenza")
            margine = gr.Slider(0, 30, value=0, step=1,
                                label="Margine attorno al riquadro (%)")
            btn = gr.Button("Trova il pianoforte", variant="primary")
        with gr.Column():
            out_ann = gr.Image(label="Rilevazione (verde = riquadro scelto)")
            out_crop = gr.Image(label="Ritaglio del pianoforte")
            out_json = gr.Code(label="Coordinate", language="json")

    btn.click(analizza, [inp, modello, conf, margine],
              [out_ann, out_crop, out_json])

if __name__ == "__main__":
    demo.launch()
