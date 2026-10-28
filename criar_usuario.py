"""Cria o usuário de acesso (ou troca a senha dele). Rode no terminal: python criar_usuario.py

A senha é digitada sem aparecer na tela e guardada só como hash.
Também cria a tabela de usuários se ela ainda não existir (pode rodar quantas vezes quiser).
"""
import getpass
import sqlite3
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

DATABASE = "studio.db"
TAMANHO_MINIMO = 10


def main():
    nome = input("Nome de usuário: ").strip()
    if not nome:
        sys.exit("O nome de usuário não pode ficar vazio.")

    senha = getpass.getpass(f"Senha (mínimo {TAMANHO_MINIMO} caracteres): ")
    if len(senha) < TAMANHO_MINIMO:
        sys.exit(f"Senha curta demais: use pelo menos {TAMANHO_MINIMO} caracteres.")
    if senha != getpass.getpass("Repita a senha: "):
        sys.exit("As senhas não conferem.")

    db = sqlite3.connect(DATABASE)
    db.executescript(Path("schema.sql").read_text(encoding="utf-8"))  # só cria o que falta
    db.execute(
        "INSERT INTO usuarios (nome, senha_hash) VALUES (?, ?) "
        "ON CONFLICT(nome) DO UPDATE SET senha_hash = excluded.senha_hash, "
        "tentativas_falhas = 0, bloqueado_ate = NULL",
        (nome, generate_password_hash(senha)),
    )
    db.commit()
    db.close()
    print("Usuário salvo.")


if __name__ == "__main__":
    main()
