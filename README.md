# OCR Handwriting Tool

Erkennt Handschriften auf bereits gescannten Dokumenten (Ablieferbelege, Formulare etc.) deutlich besser als Standard-Scanner-OCR.

## Engines

| Engine | Stärke | Geschwindigkeit |
|--------|--------|-----------------|
| **EasyOCR** (Standard) | Gute Handschrift-Erkennung, Deutsch + Englisch | Schnell |
| **TrOCR** (Microsoft) | Beste Handschrift-Erkennung (Transformer-Modell) | Langsamer, braucht mehr RAM |

## Installation

```bash
# System-Abhängigkeit für PDF-Support
sudo apt install poppler-utils

# Python-Pakete
pip install -r requirements.txt
```

## Verwendung

```bash
# Einzelnes Bild scannen
python ocr_handwriting.py scan.png

# PDF mit mehreren Seiten
python ocr_handwriting.py ablieferbeleg.pdf

# Ganzen Ordner verarbeiten
python ocr_handwriting.py ./scans/

# TrOCR für beste Handschrift-Erkennung
python ocr_handwriting.py scan.png --engine trocr

# Beide Engines vergleichen
python ocr_handwriting.py scan.png --engine both

# Ergebnis in Datei speichern
python ocr_handwriting.py scan.png --output ergebnis.txt

# Niedrigerer Confidence-Schwellwert (erkennt mehr, aber auch Fehler)
python ocr_handwriting.py scan.png --confidence 0.1
```

## Optionen

| Option | Beschreibung |
|--------|-------------|
| `--engine` | `easyocr` (Standard), `trocr` oder `both` |
| `--lang` | Sprachen für EasyOCR, z.B. `--lang de en` (Standard) |
| `--confidence` | Min. Confidence 0.0-1.0 (Standard: 0.2) |
| `--output` / `-o` | Ergebnis in Datei speichern |
| `--no-confidence` | Confidence-Werte ausblenden |

## Tipps für Max

- **Scans mit 300 DPI** einscannen für beste Ergebnisse
- Bei unleserlichen Handschriften: `--engine trocr` nutzen
- Bei gemischten Dokumenten (Druck + Handschrift): `--engine both` zum Vergleichen
- Ganzen Scan-Ordner auf einmal verarbeiten spart Zeit
