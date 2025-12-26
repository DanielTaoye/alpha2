import os
import logging
import sys
from pathlib import Path
from flask import Flask, jsonify, request, render_template

# 禁用日志，避免混入控制台输出（保持纯文本）
logging.disable(logging.CRITICAL)

# 确保能导入 backend/scripts 下的诊断脚本（与 diagnose_r_plugins.py 自己的做法一致）
backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 复用现有诊断逻辑
from scripts.diagnose_r_plugins import search_stock, generate_r_diagnosis_report  # noqa: E402


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/diagnose")
    def api_diagnose():
        stock = (request.args.get("stock") or "").strip()
        date = (request.args.get("date") or "").strip()
        api_base = (request.args.get("api") or os.getenv("DIAG_API_BASE_URL") or "").strip() or None

        if not stock or not date:
            return jsonify(ok=False, error="参数缺失：需要 stock 与 date(YYYY-MM-DD)"), 400

        stock_info = search_stock(stock)
        if not stock_info:
            return jsonify(ok=False, error=f"未找到股票: {stock}"), 404

        try:
            report = generate_r_diagnosis_report(stock_info, date, api_base_url=api_base)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500

        return jsonify(
            ok=True,
            stock_code=stock_info.get("code"),
            stock_name=stock_info.get("name"),
            report=report,
        )

    return app


if __name__ == "__main__":
    app = create_app()
    host = os.getenv("DIAG_HOST", "127.0.0.1")
    port = int(os.getenv("DIAG_PORT", "7000"))
    app.run(host=host, port=port, debug=False)


