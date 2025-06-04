import re
import difflib
import json
from pathlib import Path
import config

# Caminho padrão do arquivo de variantes (usado via config principal)
VARIANTS_PATH = config.VARIANTS_PATH

def load_variants():
    if VARIANTS_PATH.exists():
        try:
            with open(VARIANTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_variants(variants):
    VARIANTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(VARIANTS_PATH, "w", encoding="utf-8") as f:
        json.dump(variants, f, indent=2, ensure_ascii=False)

def add_variant(sku, field, value):
    variants = load_variants()
    sku = str(sku)
    field = str(field)
    value = str(value)
    if sku not in variants:
        variants[sku] = {}
    if field not in variants[sku]:
        variants[sku][field] = []
    if value not in variants[sku][field]:
        variants[sku][field].append(value)
        save_variants(variants)

class ValidationResult:
    def __init__(self, valid, conf, ocr_pre, ocr_pos, expected, score, variant_matched=None):
        self.valid = valid      # Boolean
        self.conf = conf        # Similarity/confidence
        self.ocr_pre = ocr_pre  # Before heuristics
        self.ocr_pos = ocr_pos  # After heuristics
        self.expected = expected
        self.score = score      # Ratio score
        self.variant_matched = variant_matched

    def __str__(self):
        status = "PASS" if self.valid else "FAIL"
        variant_info = f"(VARIANT: {self.variant_matched})" if self.variant_matched else ""
        return f"OCR_Pre='{self.ocr_pre}' | OCR_Pos='{self.ocr_pos}' | Expected='{self.expected}' | Score={self.score:.3f} | {status} {variant_info}"

def fix_capacity_ocr(text):
    if not text: return text
    t = ' '.join(text.split())
    t = re.sub(r'(\dGB)[\sIl1/\\]+(\d+GB)', r'\1 | \2', t, flags=re.IGNORECASE)
    t = t.replace('\'', '').replace('’', '').replace('`', '')
    t = t.replace('|', ' | ')
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'(\d+GB)[1\'"`”]?$', r'\1¹', t)
    return t.strip()

def fix_basic_model_ocr(text):
    if not text: return text
    t = text.strip().replace(' ', '').replace('I', '/').replace('l', '/')
    if '/' not in t and len(t) > 7:
        t = t[:7] + '/' + t[7:]
    return t

def fix_ean_ocr(text):
    return re.sub(r'\D', '', text or '')

def fix_color_ocr(text):
    return re.sub(r'[^A-Za-zÀ-ÿ]', '', text or '').upper()

def normalize_capacity(text):
    if not isinstance(text, str):
        return text
    t = text.strip()
    t = re.sub(r'(\dGB)[\sIl1/\\]+(\d+GB)', r'\1 | \2', t, flags=re.IGNORECASE)
    t = re.sub(r'(\d+GB)[1\'"`”]?$', r'\1¹', t)
    t = t.replace('|', ' | ')
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def levenshtein_score(a, b):
    if not a or not b:
        return 0.0
    seq = difflib.SequenceMatcher(None, a, b)
    return seq.ratio()

def validate_field(field, ocr, expected, sku_variants=None, sku=None):
    variants = sku_variants if sku_variants is not None else (load_variants() if sku else {})
    val = ocr or ""
    exp = expected or ""
    variants_list = []
    if sku and field and sku in variants and field in variants[sku]:
        variants_list = variants[sku][field]

    field_lower = field.lower()
    ocr_pre = val

    # Pós-processamento
    if field_lower == "capacity":
        ocr_pos = normalize_capacity(val)
        exp_pos = normalize_capacity(exp)
        compare_to = [exp_pos] if exp_pos else []
        compare_to += [normalize_capacity(v) for v in variants_list]
    elif field_lower == "basic model":
        ocr_pos = fix_basic_model_ocr(val)
        exp_pos = fix_basic_model_ocr(exp)
        compare_to = [exp_pos] if exp_pos else []
        compare_to += [fix_basic_model_ocr(v) for v in variants_list]
    elif field_lower == "ean":
        ocr_pos = fix_ean_ocr(val)
        exp_pos = fix_ean_ocr(exp)
        compare_to = [exp_pos] if exp_pos else []
        compare_to += [fix_ean_ocr(v) for v in variants_list]
    elif field_lower == "color":
        ocr_pos = fix_color_ocr(val)
        exp_pos = fix_color_ocr(exp)
        compare_to = [exp_pos] if exp_pos else []
        compare_to += [fix_color_ocr(v) for v in variants_list]
    else:
        ocr_pos = val
        exp_pos = exp
        compare_to = [exp_pos] if exp_pos else []
        compare_to += [v for v in variants_list]

    max_score = 0.0
    best_match = None
    variant_matched = None
    approved_by_variant = False

    for variant in compare_to:
        score = levenshtein_score(ocr_pos, variant)
        if score > max_score:
            max_score = score
            best_match = variant

    # Lógica revisada: PASS se score>=0.93 e:
    # - se expected existe: só PASS se igual ao expected
    # - se variante: PASS se igual a qualquer variante
    if exp:
        valid = max_score >= 0.93 and best_match == exp_pos
    elif variants_list and max_score >= 0.93 and best_match in variants_list:
        valid = True
        approved_by_variant = True
        variant_matched = best_match
    else:
        valid = False

    # Corrige caso em que o expected está diferente mas o valor bate 100% numa variante
    if not valid and variants_list and max_score >= 0.93 and best_match in variants_list:
        valid = True
        approved_by_variant = True
        variant_matched = best_match

    return ValidationResult(valid, max_score, ocr_pre, ocr_pos, exp, max_score, variant_matched=variant_matched)

def log_metrics(metrics_path, base, all_label_results, user_ip="N/A"):
    """Salva o arquivo metrics.txt formatado, extendido com logs por campo."""
    total_labels = len(all_label_results)
    total_fails = 0
    crops_pequenos = 0
    n_fields = 0
    with open(metrics_path, "w", encoding="utf-8") as f:
        f.write(f"==== {base} ====\n")
        f.write(f"UserIP: {user_ip}\n")
        for idx, label in enumerate(all_label_results):
            f.write(f"Label #{idx+1}:\n")
            for fld, res in label.items():
                variant_info = f"(VARIANT: {res.variant_matched})" if hasattr(res, "variant_matched") and res.variant_matched else ""
                f.write(
                    f"  {fld}: OCR_Pre='{getattr(res,'ocr_pre','-')}' | OCR_Pos='{getattr(res,'ocr_pos','-')}' | Expected='{getattr(res,'expected','-')}' | "
                    f"Score={getattr(res,'score',0):.3f} | {'PASS' if getattr(res,'valid',False) else 'FAIL'} {variant_info}\n"
                )
                if not getattr(res, 'valid', False):
                    total_fails += 1
                n_fields = max(n_fields, len(label))
        if total_labels > 0 and n_fields > 0:
            fail_rate = 100 * total_fails / (total_labels * n_fields)
            f.write(f"Summary: Total Labels: {total_labels} | Total fails: {total_fails} | Fail rate: {fail_rate:.1f}%\n")
            f.write(f"Crops pequenos: {crops_pequenos}/{total_labels*n_fields}\n")
        else:
            f.write("Summary: No labels detected.\n")
