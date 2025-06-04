Readme.md

# Label Check App

A powerful and modular application for **automatic label inspection** using Python, YOLO, EasyOCR, and self-learning capabilities.

## Features

- **Automatic Label Detection**: Uses YOLO (nano) for detecting label regions and fields.
- **Text Extraction**: Uses EasyOCR for robust OCR of printed and handwritten text on labels.
- **Barcode Decoding**: Decodes EAN and other barcodes from label images using ZXing.
- **SKU Auto-Selection**: Automatically identifies which SKU to use based on G-MES logs.
- **Self-Learning**: When a field fails, user can approve it as a valid variant, which is added to `sku_variants.json`.
- **Modular Pipeline**: Pipeline covers loading, detection, field parsing, OCR, barcode reading, self-learning, and logging.
- **GUI with Debug Mode**: Interactive interface with debug mode for reviewing and approving failed fields.
- **Extensive Logging**: All processing steps are logged for easy troubleshooting.

## Project Structure

- `main.py` – Core pipeline and logic.
- `gui.py` – Graphical interface for user interaction.
- `ocr_utils.py` – OCR and text normalization utilities.
- `validation.py` – Field validation, variants, and self-learning logic.
- `gmes_check.py` – Log parser for automatic SKU detection.
- `YOLO/` – YOLO model weights (`yolo_label_detector.pt`, `yolo_field_detector.pt`).
- `Model File/` – `SKU List.ini` (reference SKUs), `sku_variants.json` (auto-learned variants).
- `.EasyOCR/model/` – OCR model files (`craft_mlt_25k.pth`, `latin_g2.pth`).

## How it works

1. **SKU is automatically selected** from the G-MES log file.
2. **Image is processed**: labels detected with YOLO, fields parsed, OCR performed.
3. **Each field is validated** against expected value and variants.
4. **If a field fails**, in debug mode, user can approve as variant for future auto-approval (self-learning).
5. **Results and logs are saved** for review.

## Setup

1. Download or clone this repository.
2. Make sure you have Python 3.8+ and required dependencies from `requirements.txt`.
3. Place model files and config files as shown in the structure.
4. Run `gui.py` for the graphical interface.

## License

MIT License.