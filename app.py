import sqlite3
from datetime import date

from flask import Flask, g, render_template

app = Flask(__name__)
DATABASE = "studio.db"


def get_db():
    """Abre uma conexão por requisição e reaproveita dentro dela."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.template_filter("brl")
def brl(centavos):
    """8000 -> 'R$ 80,00'"""
    texto = f"{centavos / 100:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


@app.route("/")
def resumo():
    mes = date.today().strftime("%Y-%m")
    db = get_db()

    entrou = db.execute(
        "SELECT COALESCE(SUM(recebido_centavos), 0) FROM atendimentos "
        "WHERE strftime('%Y-%m', data) = ?",
        (mes,),
    ).fetchone()[0]

    saiu = db.execute(
        "SELECT COALESCE(SUM(valor_centavos), 0) FROM saidas "
        "WHERE strftime('%Y-%m', data) = ?",
        (mes,),
    ).fetchone()[0]

    return render_template("resumo.html", mes=mes, entrou=entrou, saiu=saiu, lucro=entrou - saiu)
