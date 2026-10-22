import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Flask, g, redirect, render_template, request, url_for

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


@app.template_filter("data_br")
def data_br(texto):
    """'2026-10-22' -> '22/10/2026'"""
    return "/".join(reversed(texto.split("-")))


def reais_para_centavos(texto):
    """'50,00', '1.234,56' ou '50.5' -> centavos (int). Levanta ValueError se inválido."""
    limpo = texto.replace("R$", "").strip()
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(limpo)
    except InvalidOperation:
        raise ValueError("valor inválido")
    if not valor.is_finite() or valor <= 0:
        raise ValueError("valor inválido")
    return int((valor * 100).quantize(Decimal(1)))


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


@app.route("/saidas")
def saidas():
    linhas = get_db().execute(
        "SELECT s.id, s.data, c.nome AS categoria, s.valor_centavos, s.descricao "
        "FROM saidas s JOIN categorias c ON c.id = s.categoria_id "
        "ORDER BY s.data DESC, s.id DESC LIMIT 50"
    ).fetchall()
    return render_template("saidas.html", saidas=linhas)


@app.route("/saidas/nova", methods=["GET", "POST"])
def saida_nova():
    db = get_db()
    categorias = db.execute(
        "SELECT id, nome FROM categorias WHERE tipo = 'saida' ORDER BY nome"
    ).fetchall()
    ids_validos = {str(c["id"]) for c in categorias}

    form = {"data": date.today().isoformat(), "categoria_id": "", "valor": "", "descricao": ""}
    erro = None

    if request.method == "POST":
        form = {campo: request.form.get(campo, "").strip() for campo in form}

        if form["categoria_id"] not in ids_validos:
            erro = "Escolha uma categoria."
        else:
            try:
                valor = reais_para_centavos(form["valor"])
            except ValueError:
                erro = "Informe um valor válido, como 50,00."

        if not erro:
            try:
                data_lancamento = date.fromisoformat(form["data"])
            except ValueError:
                erro = "Informe uma data válida."

        if not erro:
            db.execute(
                "INSERT INTO saidas (data, categoria_id, valor_centavos, descricao) "
                "VALUES (?, ?, ?, ?)",
                (data_lancamento.isoformat(), int(form["categoria_id"]), valor, form["descricao"] or None),
            )
            db.commit()
            return redirect(url_for("saidas"))

    return render_template("saida_nova.html", categorias=categorias, form=form, erro=erro)
