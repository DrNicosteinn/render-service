from flask import Flask, request, jsonify, send_file
import subprocess
import tempfile
import os
import uuid

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/preview", methods=["POST"])
def preview():
    """SVG → PNG (72 DPI) fuer Vorschau"""
    try:
        svg_content = request.data.decode("utf-8")
        job_id = request.args.get("job_id", str(uuid.uuid4()))

        tmpdir = tempfile.mkdtemp()
        svg_path = os.path.join(tmpdir, f"{job_id}.svg")
        png_path = os.path.join(tmpdir, f"{job_id}.png")

        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_content)

        # Inkscape: SVG → PNG bei 72 DPI
        result = subprocess.run([
            "inkscape",
            svg_path,
            "--export-type=png",
            f"--export-filename={png_path}",
            "--export-dpi=72"
        ], capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            return jsonify({
                "error": f"Inkscape Fehler (code {result.returncode})",
                "stderr": result.stderr[-2000:],
                "stdout": result.stdout[-500:]
            }), 500

        files_in_dir = os.listdir(tmpdir)
        if not os.path.exists(png_path):
            return jsonify({
                "error": "PNG wurde nicht erstellt",
                "inkscape_stdout": result.stdout[-500:],
                "inkscape_stderr": result.stderr[-2000:],
                "files_in_tmpdir": files_in_dir,
                "svg_size_bytes": os.path.getsize(svg_path)
            }), 500

        return send_file(
            png_path,
            mimetype="image/png",
            as_attachment=False
        )

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Inkscape Timeout (>60s)"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/print", methods=["POST"])
def print_file():
    """SVG → PDF/X (300 DPI, CMYK) fuer Druck – erst nach Bestellung"""
    try:
        svg_content = request.data.decode("utf-8")
        job_id = request.args.get("job_id", str(uuid.uuid4()))

        tmpdir = tempfile.mkdtemp()
        svg_path = os.path.join(tmpdir, f"{job_id}.svg")
        pdf_path = os.path.join(tmpdir, f"{job_id}.pdf")
        pdfx_path = os.path.join(tmpdir, f"{job_id}_print.pdf")

        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_content)

        # Inkscape: SVG → PDF bei 300 DPI
        result = subprocess.run([
            "inkscape",
            svg_path,
            "--export-type=pdf",
            f"--export-filename={pdf_path}",
            "--export-dpi=300"
        ], capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            return jsonify({"error": f"Inkscape Fehler: {result.stderr}"}), 500

        # Ghostscript: PDF → PDF/X mit CMYK
        gs_result = subprocess.run([
            "gs",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=pdfwrite",
            "-dPDFX",
            "-sColorConversionStrategy=CMYK",
            "-dProcessColorModel=/DeviceCMYK",
            f"-sOutputFile={pdfx_path}",
            pdf_path
        ], capture_output=True, text=True, timeout=120)

        if gs_result.returncode != 0:
            return jsonify({"error": f"Ghostscript Fehler: {gs_result.stderr}"}), 500

        return send_file(
            pdfx_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{job_id}_print.pdf"
        )

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Render Timeout"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
