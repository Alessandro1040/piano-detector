"""Video -> mani.json: i polpastrelli di TUTTE le mani visibili (1, 2, 3...), frame per frame.
Se hai gia' i landmark da hands.py, basta scrivere lo stesso formato:
  {"frames": [ [[x,y],[x,y],...],  ... ]}   (pixel del frame, un elenco di punti per frame)

Nota: usa l'API Tasks (mediapipe.tasks.python.vision.HandLandmarker), perche' l'API
a "solutions" (mp.solutions.hands) e' stata rimossa da mediapipe >= 0.10.31.
Serve il modello hand_landmarker.task (7.5 MB), di solito in weights/.
"""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np

PUNTE = (4, 8, 12, 16, 20)          # pollice, indice, medio, anulare, mignolo
URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
       "hand_landmarker/float16/1/hand_landmarker.task")

a = argparse.ArgumentParser()
a.add_argument("video")
a.add_argument("-o", default="mani.json")
a.add_argument("--max-mani", type=int, default=6)
a.add_argument("--tieni", type=int, default=4,
               help="se le mani spariscono per pochi frame, riusa l'ultima posizione")
a.add_argument("--soglia", type=float, default=0.4)
a.add_argument("--modello", default=None,
               help="percorso di hand_landmarker.task (default: weights/ o ../weights/)")
a = a.parse_args()

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
except ImportError as e:
    raise SystemExit(
        f"mediapipe non utilizzabile ({e}).\n"
        f"Installa con:  python3 -m pip install mediapipe\n"
        f"e scarica il modello:  {URL}\nsalvandolo come weights/hand_landmarker.task"
    ) from e

def trova_modello(p):
    if p:
        return Path(p)
    for c in (Path("weights/hand_landmarker.task"),
              Path("../weights/hand_landmarker.task"),
              Path("hand_landmarker.task")):
        if c.is_file():
            return c
    raise SystemExit(f"modello delle mani non trovato.\nScaricalo da:\n    {URL}\n"
                     f"e salvalo come weights/hand_landmarker.task")

modello = trova_modello(a.modello)
opzioni = vision.HandLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path=str(modello)),
    running_mode=vision.RunningMode.VIDEO,
    num_hands=a.max_mani,
    min_hand_detection_confidence=a.soglia,
    min_hand_presence_confidence=a.soglia,
    min_tracking_confidence=a.soglia,
)
H = vision.HandLandmarker.create_from_options(opzioni)

cap = cv2.VideoCapture(a.video)
if not cap.isOpened():
    raise SystemExit(f"impossibile aprire il video: {a.video}")
fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
out, ultimo, buchi, j = [], [], 0, 0
while True:
    ok, f = cap.read()
    if not ok:
        break
    h, w = f.shape[:2]
    rgb = np.ascontiguousarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    r = H.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                           int(round(j * 1000.0 / fps)))
    j += 1
    pts = []
    for mano in (r.hand_landmarks or []):
        for i in PUNTE:
            if i < len(mano):
                pts.append([float(mano[i].x) * w, float(mano[i].y) * h])
    if pts:
        ultimo, buchi = pts, 0
    else:
        buchi += 1
        pts = ultimo if buchi <= a.tieni else []
    out.append(pts)
cap.release()
H.close()
json.dump({"frames": out}, open(a.o, "w"))
print(len(out), "frame,", sum(1 for p in out if p), "con mani")
