"""Cria o banco (studio.db) e as categorias iniciais. Pode rodar mais de uma vez."""
import sqlite3
from pathlib import Path

DATABASE = "studio.db"

CATEGORIAS = [
    ("Perfuração", "entrada"),
    ("Lobuloplastia", "entrada"),
    ("Venda de joia", "entrada"),
    ("Material descartável", "saida"),
    ("Compra de joias (estoque)", "saida"),
    ("Alimentação / recepção", "saida"),
    ("Funcionária: fixo semanal", "saida"),
    ("Funcionária: comissão", "saida"),
    ("Gestão do patrocinado", "saida"),
    ("Anúncios (Facebook)", "saida"),
    ("Água", "saida"),
    ("Luz", "saida"),
    ("Outros", "saida"),
]

SERVICOS_PERFURACAO = ["Lóbulo", "Umbigo", "Peito", "Aba Nasal","Hélix", "Conch","Tragus", "Rook", "Daith", "Australianos", "Flat", "Minion", "Anti-Hélix", "Outros"]


def main():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(Path("schema.sql").read_text(encoding="utf-8"))

    db.executemany(
        "INSERT OR IGNORE INTO categorias (nome, tipo) VALUES (?, ?)", CATEGORIAS
    )
    perfuracao_id = db.execute(
        "SELECT id FROM categorias WHERE nome = 'Perfuração'"
    ).fetchone()[0]
    db.executemany(
        "INSERT OR IGNORE INTO servicos (nome, categoria_id) VALUES (?, ?)",
        [(nome, perfuracao_id) for nome in SERVICOS_PERFURACAO],
    )

    db.commit()
    db.close()
    print("Banco pronto:", DATABASE)


if __name__ == "__main__":
    main()
