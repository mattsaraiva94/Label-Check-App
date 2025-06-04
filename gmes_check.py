import os
import re
from pathlib import Path
import config

def find_latest_gmes_log(ip=None, log_dir=Path(config.SKU_PATH)):
    """
    Procura o arquivo de log mais recente que contenha 'gumi' e, se ip informado, também o IP no nome.
    """
    files = [f for f in Path(log_dir).glob("*gumi*.txt")]
    if ip:
        ip_clean = ip.replace(".", "")
        files = [f for f in files if ip_clean in f.name or ip in f.name]
    if not files:
        return None
    # Pega o mais recente pelo mtime
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return latest

def extract_last_sku_from_log(log_path):
    """
    Lê o log e extrai o ÚLTIMO SKU em formato MODEL:[SKU].
    """
    sku = None
    if not log_path or not os.path.exists(log_path):
        return None
    regex = re.compile(r"MODEL:$begin:math:display$([A-Z0-9\\-]+)$end:math:display$")
    with open(log_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            matches = regex.findall(line)
            if matches:
                sku = matches[-1]  # sempre pega o último SKU da linha
    return sku
