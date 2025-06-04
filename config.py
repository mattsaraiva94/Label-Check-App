from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).parent

# Path to the teaching INI file (tab-delimited)
TEACHING_INI = BASE_DIR / 'Model File' / 'SKU List.ini'

# Path to SKU variants JSON
SKU_VARIANTS_PATH = BASE_DIR / 'Model File' / 'sku_variants.json'

# Caminho padrão do arquivo de variantes (referência para outros módulos)
VARIANTS_PATH = SKU_VARIANTS_PATH

# Folder to watch incoming SKU log (G-MES integration)
SKU_PATH = r"C:\G-MES2.0\SEDA_WEB\log"

# Folder to watch for incoming test images
WATCH_FOLDER = r'C:/MBPS - Final/MBPS_PC_SEVT/log_img'

# YOLO model paths (trained by user)
YOLO1_MODEL_PATH = BASE_DIR / 'YOLO' / 'yolo_label_detector.pt'
YOLO2_MODEL_PATH = BASE_DIR / 'YOLO' / 'yolo_field_detector.pt'

# EasyOCR custom model folder (set this for offline mode)
EASYOCR_MODEL_DIR = BASE_DIR / '.EasyOCR' / 'model'
