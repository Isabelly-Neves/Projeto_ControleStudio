import sqlite3
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from flask import Flask, abort, g, redirect, render_template, request, url_for

app = Flask(__name__)
DATABASE = "studio.db"

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

FORMAS_PAGAMENTO = [
    ("pix", "Pix"),
    ("dinheiro", "Dinheiro"),
    ("credito", "Cartão de crédito"),
    ("debito", "Cartão de débito"),
]


# ---------- banco de dados ----------

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


# ---------- formatação e conversão de valores ----------

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


def centavos_para_reais(centavos):
    """12345 -> '123,45' (para preencher campos de formulário na edição)"""
    return f"{centavos / 100:.2f}".replace(".", ",")


# ---------- resumo ----------

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


# ---------- saídas ----------

@app.route("/saidas")
def saidas():
    linhas = get_db().execute(
        "SELECT s.id, s.data, c.nome AS categoria, s.valor_centavos, s.descricao "
        "FROM saidas s JOIN categorias c ON c.id = s.categoria_id "
        "ORDER BY s.data DESC, s.id DESC LIMIT 50"
    ).fetchall()
    return render_template("saidas.html", saidas=linhas)


@app.route("/saidas/nova", methods=["GET", "POST"])
@app.route("/saidas/<int:saida_id>/editar", methods=["GET", "POST"])
def saida_form(saida_id=None):
    """Mesma tela para criar (sem id) e para editar (com id)."""
    db = get_db()
    categorias = db.execute(
        "SELECT id, nome FROM categorias WHERE tipo = 'saida' ORDER BY nome"
    ).fetchall()
    ids_validos = {str(c["id"]) for c in categorias}

    form = {"data": date.today().isoformat(), "categoria_id": "", "valor": "", "descricao": ""}
    if saida_id is not None:
        saida = db.execute("SELECT * FROM saidas WHERE id = ?", (saida_id,)).fetchone()
        if saida is None:
            abort(404)
        form = {
            "data": saida["data"],
            "categoria_id": str(saida["categoria_id"]),
            "valor": centavos_para_reais(saida["valor_centavos"]),
            "descricao": saida["descricao"] or "",
        }
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
            dados = (data_lancamento.isoformat(), int(form["categoria_id"]), valor, form["descricao"] or None)
            if saida_id is None:
                db.execute(
                    "INSERT INTO saidas (data, categoria_id, valor_centavos, descricao) "
                    "VALUES (?, ?, ?, ?)",
                    dados,
                )
            else:
                db.execute(
                    "UPDATE saidas SET data = ?, categoria_id = ?, valor_centavos = ?, descricao = ? "
                    "WHERE id = ?",
                    (*dados, saida_id),
                )
            db.commit()
            return redirect(url_for("saidas"))

    return render_template(
        "saida_form.html", categorias=categorias, form=form, erro=erro,
        editando=saida_id is not None, saida_id=saida_id,
    )


@app.route("/saidas/<int:saida_id>/apagar", methods=["POST"])
def saida_apagar(saida_id):
    db = get_db()
    db.execute("DELETE FROM saidas WHERE id = ?", (saida_id,))
    db.commit()
    return redirect(url_for("saidas"))


# ---------- atendimentos ----------

def opcoes_de_itens(db):
    """O que pode ser cobrado em um atendimento: cada serviço (com sua categoria)
    e cada categoria de entrada que não tem serviços (ex.: Venda de joia)."""
    opcoes = []
    servicos = db.execute(
        "SELECT s.id, s.nome, c.id AS categoria_id, c.nome AS categoria "
        "FROM servicos s JOIN categorias c ON c.id = s.categoria_id "
        "WHERE c.tipo = 'entrada'"
    ).fetchall()
    for s in servicos:
        opcoes.append({
            "valor": f"s:{s['id']}",
            "rotulo": f"{s['categoria']}: {s['nome']}",
            "categoria_id": s["categoria_id"],
            "servico_id": s["id"],
        })
    categorias = db.execute(
        "SELECT id, nome FROM categorias "
        "WHERE tipo = 'entrada' AND id NOT IN (SELECT categoria_id FROM servicos)"
    ).fetchall()
    for c in categorias:
        opcoes.append({
            "valor": f"c:{c['id']}",
            "rotulo": c["nome"],
            "categoria_id": c["id"],
            "servico_id": None,
        })
    return sorted(opcoes, key=lambda o: o["rotulo"])


@app.route("/atendimentos")
def atendimentos():
    linhas = get_db().execute(
        "SELECT a.id, a.data, a.cliente, a.forma_pagamento, a.recebido_centavos, "
        "       a.agendado_por, a.descricao, "
        "       SUM(i.valor_centavos) AS total, "
        "       GROUP_CONCAT(COALESCE(s.nome, c.nome), ', ') AS itens "
        "FROM atendimentos a "
        "JOIN itens_atendimento i ON i.atendimento_id = a.id "
        "JOIN categorias c ON c.id = i.categoria_id "
        "LEFT JOIN servicos s ON s.id = i.servico_id "
        "GROUP BY a.id "
        "ORDER BY a.data DESC, a.id DESC LIMIT 50"
    ).fetchall()
    return render_template("atendimentos.html", atendimentos=linhas, formas=dict(FORMAS_PAGAMENTO))


@app.route("/atendimentos/novo", methods=["GET", "POST"])
@app.route("/atendimentos/<int:atendimento_id>/editar", methods=["GET", "POST"])
def atendimento_form(atendimento_id=None):
    """Mesma tela para criar (sem id) e para editar (com id)."""
    db = get_db()
    opcoes = opcoes_de_itens(db)
    por_valor = {o["valor"]: o for o in opcoes}
    pessoas = [
        r[0] for r in db.execute(
            "SELECT DISTINCT agendado_por FROM atendimentos "
            "WHERE agendado_por IS NOT NULL ORDER BY agendado_por"
        )
    ]

    form = {
        "data": date.today().isoformat(), "cliente": "", "forma_pagamento": "pix",
        "recebido": "", "agendado_por": "", "descricao": "",
    }
    linhas = [{"item": "", "valor": ""}]

    if atendimento_id is not None:
        a = db.execute("SELECT * FROM atendimentos WHERE id = ?", (atendimento_id,)).fetchone()
        if a is None:
            abort(404)
        salvos = db.execute(
            "SELECT categoria_id, servico_id, valor_centavos FROM itens_atendimento "
            "WHERE atendimento_id = ? ORDER BY id",
            (atendimento_id,),
        ).fetchall()
        total_salvo = sum(i["valor_centavos"] for i in salvos)
        form = {
            "data": a["data"],
            "cliente": a["cliente"] or "",
            "forma_pagamento": a["forma_pagamento"],
            "recebido": "" if a["recebido_centavos"] == total_salvo else centavos_para_reais(a["recebido_centavos"]),
            "agendado_por": a["agendado_por"] or "",
            "descricao": a["descricao"] or "",
        }
        linhas = [
            {
                "item": f"s:{i['servico_id']}" if i["servico_id"] else f"c:{i['categoria_id']}",
                "valor": centavos_para_reais(i["valor_centavos"]),
            }
            for i in salvos
        ]
    erro = None

    if request.method == "POST":
        form = {campo: request.form.get(campo, "").strip() for campo in form}
        enviados = zip(request.form.getlist("item"), request.form.getlist("valor_item"))
        linhas = [{"item": i, "valor": v.strip()} for i, v in enviados] or linhas

        # 1) itens: ignora linhas totalmente em branco, valida as outras
        itens = []
        for linha in linhas:
            if not linha["item"] and not linha["valor"]:
                continue
            opcao = por_valor.get(linha["item"])
            try:
                valor = reais_para_centavos(linha["valor"])
            except ValueError:
                valor = None
            if opcao is None or valor is None:
                erro = "Cada item precisa de um serviço e de um valor válido, como 90,00."
                break
            itens.append((opcao["categoria_id"], opcao["servico_id"], valor))
        if not erro and not itens:
            erro = "Adicione pelo menos um item."

        # 2) total e quanto caiu na conta (vazio = igual ao total)
        total = sum(item[2] for item in itens)
        recebido = total
        if not erro and form["recebido"]:
            try:
                recebido = reais_para_centavos(form["recebido"])
            except ValueError:
                erro = "Informe um valor válido em \"Quanto caiu na conta\", como 85,50."
            else:
                if recebido > total:
                    erro = "O valor que caiu na conta não pode ser maior que o total dos itens."

        # 3) forma de pagamento e data
        if not erro and form["forma_pagamento"] not in dict(FORMAS_PAGAMENTO):
            erro = "Escolha a forma de pagamento."
        if not erro:
            try:
                data_atendimento = date.fromisoformat(form["data"])
            except ValueError:
                erro = "Informe uma data válida."

        # 4) salva tudo junto: ou grava o atendimento com todos os itens, ou nada
        if not erro:
            dados = (
                data_atendimento.isoformat(), form["cliente"] or None,
                form["forma_pagamento"], recebido,
                form["agendado_por"] or None, form["descricao"] or None,
            )
            with db:
                if atendimento_id is None:
                    cursor = db.execute(
                        "INSERT INTO atendimentos "
                        "(data, cliente, forma_pagamento, recebido_centavos, agendado_por, descricao) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        dados,
                    )
                    id_salvo = cursor.lastrowid
                else:
                    db.execute(
                        "UPDATE atendimentos SET data = ?, cliente = ?, forma_pagamento = ?, "
                        "recebido_centavos = ?, agendado_por = ?, descricao = ? WHERE id = ?",
                        (*dados, atendimento_id),
                    )
                    # na edição, os itens antigos são trocados pelos novos
                    db.execute("DELETE FROM itens_atendimento WHERE atendimento_id = ?", (atendimento_id,))
                    id_salvo = atendimento_id
                db.executemany(
                    "INSERT INTO itens_atendimento "
                    "(atendimento_id, categoria_id, servico_id, valor_centavos) "
                    "VALUES (?, ?, ?, ?)",
                    [(id_salvo, *item) for item in itens],
                )
            return redirect(url_for("atendimentos"))

    return render_template(
        "atendimento_form.html", form=form, linhas=linhas, opcoes=opcoes,
        pessoas=pessoas, formas=FORMAS_PAGAMENTO, erro=erro,
        editando=atendimento_id is not None, atendimento_id=atendimento_id,
    )


@app.route("/atendimentos/<int:atendimento_id>/apagar", methods=["POST"])
def atendimento_apagar(atendimento_id):
    db = get_db()
    # os itens somem junto (ON DELETE CASCADE no schema)
    db.execute("DELETE FROM atendimentos WHERE id = ?", (atendimento_id,))
    db.commit()
    return redirect(url_for("atendimentos"))


# ---------- faturamento por serviço ----------

@app.route("/faturamento")
def faturamento():
    hoje = date.today()
    try:
        primeiro = date.fromisoformat(request.args.get("mes", "") + "-01")
    except ValueError:
        primeiro = hoje.replace(day=1)
    mes = primeiro.strftime("%Y-%m")
    anterior = (primeiro - timedelta(days=1)).strftime("%Y-%m")
    proximo = (primeiro + timedelta(days=32)).strftime("%Y-%m")

    linhas = get_db().execute(
        "SELECT COALESCE(s.nome, c.nome) AS nome, c.nome AS categoria, "
        "       COUNT(*) AS quantidade, SUM(i.valor_centavos) AS total "
        "FROM itens_atendimento i "
        "JOIN atendimentos a ON a.id = i.atendimento_id "
        "JOIN categorias c ON c.id = i.categoria_id "
        "LEFT JOIN servicos s ON s.id = i.servico_id "
        "WHERE strftime('%Y-%m', a.data) = ? "
        "GROUP BY i.categoria_id, i.servico_id "
        "ORDER BY total DESC, nome",
        (mes,),
    ).fetchall()

    total = sum(linha["total"] for linha in linhas)
    servicos = [
        {
            "nome": l["nome"], "quantidade": l["quantidade"], "total": l["total"],
            "pct": round(l["total"] * 100 / total),
        }
        for l in linhas
    ]

    por_categoria = {}
    for l in linhas:
        por_categoria[l["categoria"]] = por_categoria.get(l["categoria"], 0) + l["total"]
    categorias = sorted(por_categoria.items(), key=lambda par: par[1], reverse=True)

    return render_template(
        "faturamento.html", titulo_mes=f"{MESES[primeiro.month - 1].capitalize()} de {primeiro.year}",
        anterior=anterior, proximo=proximo, tem_proximo=primeiro < hoje.replace(day=1),
        total=total, servicos=servicos, categorias=categorias,
    )
