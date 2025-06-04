import easyocr
import numpy as np
import re
import logging
import config

# Inicializa o modelo EasyOCR apontando para o diretório local de modelos (.EasyOCR/model)
reader = easyocr.Reader(
    ['pt'],
    gpu=False,
    model_storage_directory=str(config.EASYOCR_MODEL_DIR),
    download_enabled=False
)

def fix_capacity_ocr(text):
    """
    Normaliza saída OCR para campo Capacity.
    - Troca variantes de pipe/barras por |
    - Troca variantes de ¹ (aspas, acento, '1' no fim) por “¹”
    - Remove espaços extras
    """
    if not isinstance(text, str):
        return text
    # Troca pipe variantes (I, l, 1, /, \, etc) por |
    t = re.sub(r'(\dGB)[\sIl1/\\]+(\d+GB)', r'\1 | \2', text, flags=re.IGNORECASE)
    # Corrige "1" no final por "¹"
    t = re.sub(r'(\dGB)1\b', r'\1¹', t)
    t = re.sub(r'(\d+GB)\s*1$', r'\1¹', t)
    # Troca variantes de '¹'
    t = t.replace("'", "¹").replace("`", "¹").replace("’", "¹")
    # Remove espaços duplicados
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def fix_basic_model_ocr(text):
    """
    Corrige OCR de BasicModel: 'SMA266M/DS', 'SM-A266M/DS', etc.
    Força barra '/' se não tiver.
    """
    if not text:
        return text
    t = text.strip().replace(' ', '').replace('I', '/').replace('l', '/')
    if '/' not in t and len(t) > 7:
        t = t[:7] + '/' + t[7:]
    return t

def fix_ean_ocr(text):
    """Só números, remove espaços e separadores."""
    return re.sub(r'\D', '', text or '')

def fix_color_ocr(text):
    """Color: só letras e acentos, em maiúsculo."""
    return re.sub(r'[^A-Za-zÀ-ÿ]', '', text or '').upper()

def extract_text_from_image(img, field_type=None):
    """
    Extrai texto de uma imagem usando EasyOCR.
    :param img: numpy array (BGR ou RGB)
    :param field_type: se for 'capacity', aplica fix_capacity_ocr
    :return: texto reconhecido (string)
    """
    # EasyOCR espera imagem em RGB
    if len(img.shape) == 3 and img.shape[2] == 3:
        img = img[..., ::-1]  # BGR to RGB

    result = reader.readtext(img, detail=0, paragraph=False)
    logging.info(f"EasyOCR result: {result}")

    text = " ".join(result).strip()
    if not text:
        return ""
    if field_type and field_type.lower() == "capacity":
        text = fix_capacity_ocr(text)
    if field_type and field_type.lower() == "basic model":
        text = fix_basic_model_ocr(text)
    if field_type and field_type.lower() == "ean":
        text = fix_ean_ocr(text)
    if field_type and field_type.lower() == "color":
        text = fix_color_ocr(text)
    return text
