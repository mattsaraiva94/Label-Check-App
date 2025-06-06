import os
import logging
import cv2
import numpy as np
import zxingcpp
import re
from pathlib import Path
from ultralytics import YOLO
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import json
import ocr_utils
import validation
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("label_app.log"),
        logging.StreamHandler()
    ]
)

def load_variants():
    path = config.SKU_VARIANTS_PATH
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_variants(variants):
    path = config.SKU_VARIANTS_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(variants, f, indent=2, ensure_ascii=False)

def add_variant(sku, field, variant):
    variants = load_variants()
    if sku not in variants:
        variants[sku] = {}
    if field not in variants[sku]:
        variants[sku][field] = []
    if variant not in variants[sku][field]:
        variants[sku][field].append(variant)
        save_variants(variants)
        logging.info(f"Added variant: {sku} - {field} - {variant}")

class SafeYOLO:
    def __init__(self, model_path):
        self.model = YOLO(str(model_path))
        self._thread_local = threading.local()
        self._initialize_thread_model()

    def _initialize_thread_model(self):
        if not hasattr(self._thread_local, 'initialized'):
            try:
                self.model.predict(np.zeros((32, 32, 3), dtype=np.uint8), verbose=False)
                self._thread_local.initialized = True
            except Exception as e:
                logging.error(f"Thread model initialization error: {e}")
                raise

    @property
    def names(self):
        return self.model.names

    def predict(self, img):
        try:
            self._initialize_thread_model()
            return self.model.predict(img, verbose=False, stream=False)
        except Exception as e:
            logging.error(f"Prediction error: {e}")
            raise

yolo1 = SafeYOLO(config.YOLO1_MODEL_PATH)
logging.info("Loaded YOLO1 model")
yolo2 = SafeYOLO(config.YOLO2_MODEL_PATH)
logging.info("Loaded YOLO2 model")

def decode_barcode_ean(image):
    try:
        success, buf = cv2.imencode('.png', image)
        if not success:
            return ""
        arr = np.frombuffer(buf.tobytes(), dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        barcodes = zxingcpp.read_barcodes(img)
        if barcodes:
            raw = barcodes[0].text
            cleaned = re.sub(r"\D", "", raw)
            return cleaned
        return ""
    except Exception:
        logging.exception("Barcode decode exception")
        return ""

def process_image_pipeline(image_path, sku_info=None, progress_callback=None, stop_event=None, gui_update_fn=None, user_ip=None):
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read {image_path}")

    annotated = img.copy()
    res1 = yolo1.predict(img)[0]

    boxes_raw = [tuple(map(int, b.xyxy[0])) for b in res1.boxes]
    if not boxes_raw:
        boxes = []
    else:
        thresh = 30
        centers = []
        for i, (x1, y1, x2, y2) in enumerate(boxes_raw):
            centers.append((i, ((x1 + x2) // 2, (y1 + y2) // 2, x1, y1, x2, y2)))
        centers_sorted = sorted(centers, key=lambda t: (t[1][1], t[1][0]))
        rows = []
        cur_row = []
        last_y = None
        for i, (_, y, *_rest) in centers_sorted:
            if last_y is not None and abs(y - last_y) > thresh:
                rows.append(cur_row)
                cur_row = []
            cur_row.append(i)
            last_y = y
        if cur_row: rows.append(cur_row)
        order_map = []
        for row in rows:
            xs = [(idx, (boxes_raw[idx][0]+boxes_raw[idx][2])//2) for idx in row]
            xs_sorted = sorted(xs, key=lambda t: t[1])
            order_map.extend([idx for idx, _ in xs_sorted])
        boxes = [boxes_raw[i] for i in order_map]
    count = len(boxes)
    ng_labels = []
    base = Path(image_path).stem
    out_dir = config.BASE_DIR / 'logs' / base
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / 'metrics.txt'
    if metrics_path.exists():
        metrics_path.unlink()
    all_label_results = []
    sku_variants = load_variants()

    valid_fields = set()
    if sku_info:
        valid_fields = {k.strip().upper() for k in sku_info.keys() if k.strip() and k.upper() != 'SKU'}

    def handle_label(idx, coords):
        if stop_event and stop_event.is_set():
            return
        x1, y1, x2, y2 = coords
        crop_label = img[y1:y2, x1:x2]
        crop_rot = cv2.rotate(crop_label, cv2.ROTATE_90_CLOCKWISE)
        box_color = (255, 0, 0)

        cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)
        cv2.putText(annotated, f"{idx+1:02d}", (x1+5, y2-5), cv2.FONT_HERSHEY_SIMPLEX, 0.8, box_color, 2)
        if gui_update_fn:
            gui_update_fn(annotated.copy())

        logs = {}
        score_list = []

        try:
            res2 = yolo2.predict(crop_rot)[0].boxes
            fields_detected = {}
            for b in res2:
                cls = int(b.cls[0])
                raw_name = yolo2.names[cls]
                norm = raw_name.replace("_", " ").upper()
                if norm not in valid_fields:
                    continue
                fx1, fy1, fx2, fy2 = map(int, b.xyxy[0])
                crop_field = crop_rot[fy1:fy2, fx1:fx2]
                expected = sku_info.get(norm, "") if sku_info else ""
                if not expected and sku_info:
                    for key in sku_info:
                        if key.strip().upper() == norm:
                            expected = sku_info[key]
                            break
                ocr_pre, ocr_pos, score, res = "-", "-", 0.0, None
                if norm == "EAN":
                    decoded = decode_barcode_ean(crop_field)
                    ocr_pre = decoded if decoded else "-"
                    ocr_pos = decoded if decoded else ocr_utils.extract_text_from_image(crop_field)
                    res = validation.validate_field("EAN", ocr_pos, expected, sku_variants, sku_info["SKU"])
                else:
                    ocr_pre = ocr_utils.extract_text_from_image(crop_field)
                    if norm == "CAPACITY":
                        ocr_pos = validation.fix_capacity_ocr(ocr_pre)
                    elif norm == "BASIC MODEL":
                        ocr_pos = validation.fix_basic_model_ocr(ocr_pre)
                    elif norm == "COLOR":
                        ocr_pos = validation.fix_color_ocr(ocr_pre)
                    else:
                        ocr_pos = ocr_pre
                    res = validation.validate_field(norm.title(), ocr_pos, expected, sku_variants, sku_info["SKU"])
                score = res.score
                logs[norm.title()] = res
                fields_detected[norm.title()] = res
                score_list.append(score)

            mean_score = np.mean(score_list) if score_list else 0
            if mean_score > 0.95:
                box_color = (0, 255, 0)
            elif any(not v.valid for v in fields_detected.values()):
                box_color = (0, 0, 255)

            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(annotated, f"{idx+1:02d}", (x1+5, y2-5), cv2.FONT_HERSHEY_SIMPLEX, 0.8, box_color, 2)
            all_label_results.append(logs)
            if gui_update_fn:
                gui_update_fn(annotated.copy())
            ng_fields = [v for v in fields_detected.values() if not v.valid]
            if ng_fields:
                ng_labels.append({
                    "crop_img": crop_label,
                    "logs": logs,
                    "sku": sku_info["SKU"],
                    "label_num": idx + 1
                })
            if progress_callback:
                progress_callback(idx + 1, count)
        except Exception:
            logging.exception("Label task exception on label %d", idx + 1)

    with ThreadPoolExecutor(max_workers=min(4, count or 1)) as executor:
        futures = [executor.submit(handle_label, i, boxes[i]) for i in range(count)]
        for fut in as_completed(futures):
            if stop_event and stop_event.is_set():
                break
            if fut.exception():
                logging.exception("Label task exception during parallel execution")

    cv2.imwrite(str(out_dir / f"{base}_annotated.jpg"), annotated)
    validation.log_metrics(metrics_path, base, all_label_results, user_ip)
    return annotated, count, ng_labels, all_label_results 
