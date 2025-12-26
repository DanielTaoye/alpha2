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
from scripts.diagnose_r_plugins import (  # noqa: E402
    search_stock,
    search_stock_candidates,
    list_trading_dates,
    generate_r_diagnosis_report,
)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/diagnose")
    def api_diagnose():
        stock = (request.args.get("stock") or "").strip()
        date = (request.args.get("date") or "").strip()

        if not stock or not date:
            return jsonify(ok=False, error="参数缺失：需要 stock 与 date(YYYY-MM-DD)"), 400

        stock_info = search_stock(stock)
        if not stock_info:
            return jsonify(ok=False, error=f"未找到股票: {stock}"), 404

        try:
            report = generate_r_diagnosis_report(stock_info, date, api_base_url=None)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500

        return jsonify(
            ok=True,
            stock_code=stock_info.get("code"),
            stock_name=stock_info.get("name"),
            report=report,
        )

    @app.get("/api/search")
    def api_search():
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify(ok=True, items=[])
        try:
            items = search_stock_candidates(q, limit=20)
            return jsonify(ok=True, items=items)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500

    @app.get("/api/dates")
    def api_dates():
        stock = (request.args.get("stock") or "").strip()
        if not stock:
            return jsonify(ok=False, error="参数缺失：需要 stock"), 400

        stock_info = search_stock(stock)
        if not stock_info:
            return jsonify(ok=False, error=f"未找到股票: {stock}"), 404
        try:
            dates = list_trading_dates(stock_info["code"], limit=350)
            return jsonify(ok=True, stock_code=stock_info["code"], stock_name=stock_info.get("name"), dates=dates)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500

    return app


if __name__ == "__main__":
    app = create_app()
    host = os.getenv("DIAG_HOST", "127.0.0.1")
    port = int(os.getenv("DIAG_PORT", "7000"))
    app.run(host=host, port=port, debug=False)


