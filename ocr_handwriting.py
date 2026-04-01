#!/usr/bin/env python3
"""
OCR Handwriting Tool - Erkennt Handschriften auf gescannten Dokumenten.

Nutzt EasyOCR für allgemeine Texterkennung (inkl. Handschrift) und
optional TrOCR (Microsoft) für bessere Handschrift-Erkennung.

Verwendung:
    python ocr_handwriting.py bild.png
    python ocr_handwriting.py scan.pdf
    python ocr_handwriting.py ordner_mit_scans/
    python ocr_handwriting.py bild.png --engine trocr
    python ocr_handwriting.py bild.png --output ergebnis.txt
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def load_images_from_path(input_path: str) -> list[tuple[str, Image.Image]]:
    """Lädt Bilder aus Datei, PDF oder Ordner."""
    path = Path(input_path)
    results = []

    if path.is_dir():
        extensions = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".pdf"}
        for file in sorted(path.iterdir()):
            if file.suffix.lower() in extensions:
                results.extend(load_images_from_path(str(file)))
        return results

    if path.suffix.lower() == ".pdf":
        try:
            from pdf2image import convert_from_path

            images = convert_from_path(str(path), dpi=300)
            for i, img in enumerate(images):
                results.append((f"{path.name} (Seite {i + 1})", img))
        except ImportError:
            print(
                "FEHLER: pdf2image nicht installiert. "
                "Installiere mit: pip install pdf2image",
                file=sys.stderr,
            )
            print(
                "Hinweis: poppler muss auch installiert sein "
                "(apt install poppler-utils)",
                file=sys.stderr,
            )
            sys.exit(1)
        return results

    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}:
        img = Image.open(str(path))
        if img.mode != "RGB":
            img = img.convert("RGB")
        results.append((path.name, img))
        return results

    print(f"FEHLER: Nicht unterstütztes Format: {path.suffix}", file=sys.stderr)
    sys.exit(1)


def ocr_with_easyocr(
    image: Image.Image, languages: list[str], confidence_threshold: float
) -> list[dict]:
    """Führt OCR mit EasyOCR durch (gut für Handschriften)."""
    import easyocr

    reader = easyocr.Reader(languages, gpu=False)
    img_array = np.array(image)
    raw_results = reader.readtext(img_array)

    results = []
    for bbox, text, confidence in raw_results:
        if confidence >= confidence_threshold:
            results.append(
                {
                    "text": text,
                    "confidence": round(confidence, 3),
                    "bbox": bbox,
                }
            )
    return results


def ocr_with_trocr(
    image: Image.Image, confidence_threshold: float
) -> list[dict]:
    """
    Führt OCR mit TrOCR durch (Microsofts Transformer-Modell,
    spezialisiert auf Handschriften).

    TrOCR arbeitet zeilenweise - das Bild wird in Zeilen segmentiert.
    """
    try:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except ImportError:
        print(
            "FEHLER: transformers nicht installiert. "
            "Installiere mit: pip install transformers torch",
            file=sys.stderr,
        )
        sys.exit(1)

    print("  Lade TrOCR Modell (beim ersten Mal wird es heruntergeladen)...")
    processor = TrOCRProcessor.from_pretrained(
        "microsoft/trocr-base-handwritten"
    )
    model = VisionEncoderDecoderModel.from_pretrained(
        "microsoft/trocr-base-handwritten"
    )

    # Bild in horizontale Streifen aufteilen für zeilenweise Erkennung
    lines = segment_into_lines(image)
    results = []

    for i, line_img in enumerate(lines):
        pixel_values = processor(images=line_img, return_tensors="pt").pixel_values
        generated_ids = model.generate(pixel_values, max_new_tokens=128)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        text = text.strip()

        if text:
            results.append(
                {
                    "text": text,
                    "confidence": 0.0,  # TrOCR gibt kein Confidence-Score
                    "line": i + 1,
                }
            )

    return results


def segment_into_lines(image: Image.Image, min_gap: int = 15) -> list[Image.Image]:
    """
    Segmentiert ein Bild in einzelne Textzeilen anhand von
    horizontalen Leerräumen (Whitespace-Analyse).
    """
    import numpy as np

    img_array = np.array(image.convert("L"))  # Graustufen
    # Binarisieren (Otsu-ähnlich: Schwellwert bei 200)
    binary = (img_array < 200).astype(np.uint8)

    # Horizontale Projektion: Summe der dunklen Pixel pro Zeile
    row_sums = binary.sum(axis=1)

    # Zeilen finden: zusammenhängende Bereiche mit Pixeln
    in_text = False
    lines = []
    start = 0

    for y, pixel_sum in enumerate(row_sums):
        if pixel_sum > 0 and not in_text:
            start = y
            in_text = True
        elif pixel_sum == 0 and in_text:
            if y - start > min_gap:
                lines.append((max(0, start - 5), min(len(row_sums), y + 5)))
            in_text = False

    if in_text:
        lines.append((max(0, start - 5), len(row_sums)))

    # Falls keine Zeilen erkannt: ganzes Bild als eine Zeile
    if not lines:
        return [image]

    width = image.size[0]
    return [image.crop((0, top, width, bottom)) for top, bottom in lines]


def format_results(results: list[dict], show_confidence: bool = True) -> str:
    """Formatiert die OCR-Ergebnisse als lesbaren Text."""
    if not results:
        return "(Kein Text erkannt)"

    output_lines = []
    for r in results:
        text = r["text"]
        if show_confidence and r["confidence"] > 0:
            output_lines.append(f"  {text}  [{r['confidence']:.0%}]")
        else:
            output_lines.append(f"  {text}")

    return "\n".join(output_lines)


def main():
    parser = argparse.ArgumentParser(
        description="Handschrift-OCR für gescannte Dokumente (Ablieferbelege etc.)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python ocr_handwriting.py scan.png
  python ocr_handwriting.py scan.pdf --engine trocr
  python ocr_handwriting.py ./scans/ --lang de en
  python ocr_handwriting.py beleg.jpg --output ergebnis.txt
  python ocr_handwriting.py beleg.jpg --confidence 0.3
        """,
    )
    parser.add_argument(
        "input",
        help="Bild, PDF oder Ordner mit gescannten Dokumenten",
    )
    parser.add_argument(
        "--engine",
        choices=["easyocr", "trocr", "both"],
        default="easyocr",
        help="OCR-Engine: easyocr (Standard), trocr (beste Handschrift), "
        "both (beide zum Vergleich)",
    )
    parser.add_argument(
        "--lang",
        nargs="+",
        default=["de", "en"],
        help="Sprachen für EasyOCR (Standard: de en)",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.2,
        help="Minimaler Confidence-Schwellwert 0.0-1.0 (Standard: 0.2)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Ergebnis in Datei speichern statt auf Konsole",
    )
    parser.add_argument(
        "--no-confidence",
        action="store_true",
        help="Confidence-Werte nicht anzeigen",
    )

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"FEHLER: '{args.input}' nicht gefunden.", file=sys.stderr)
        sys.exit(1)

    print(f"Lade Dokument(e) aus: {args.input}")
    images = load_images_from_path(args.input)

    if not images:
        print("Keine Bilder/PDFs gefunden.", file=sys.stderr)
        sys.exit(1)

    print(f"{len(images)} Seite(n) geladen.\n")

    all_output = []

    for name, image in images:
        print(f"--- {name} ---")

        if args.engine in ("easyocr", "both"):
            print("  EasyOCR läuft...")
            results = ocr_with_easyocr(image, args.lang, args.confidence)
            header = f"[EasyOCR] {name}:"
            text = format_results(results, show_confidence=not args.no_confidence)
            print(f"\n{header}\n{text}\n")
            all_output.append(f"{header}\n{text}")

        if args.engine in ("trocr", "both"):
            print("  TrOCR (Handschrift-Spezialist) läuft...")
            results = ocr_with_trocr(image, args.confidence)
            header = f"[TrOCR] {name}:"
            text = format_results(results, show_confidence=not args.no_confidence)
            print(f"\n{header}\n{text}\n")
            all_output.append(f"{header}\n{text}")

    if args.output:
        output_text = "\n\n".join(all_output)
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Ergebnis gespeichert in: {args.output}")


if __name__ == "__main__":
    main()
