-- Valores em dinheiro ficam em CENTAVOS (inteiro): R$ 80,00 = 8000

CREATE TABLE IF NOT EXISTS categorias (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'saida'))
);

-- Detalhe das perfurações (lóbulo, hélix, umbigo, conch...)
CREATE TABLE IF NOT EXISTS servicos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nome         TEXT NOT NULL UNIQUE,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id)
);

CREATE TABLE IF NOT EXISTS eventos (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    data TEXT NOT NULL            -- formato AAAA-MM-DD
);

-- Uma visita de um cliente = um atendimento (1 pagamento)
CREATE TABLE IF NOT EXISTS atendimentos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    data              TEXT NOT NULL,          -- AAAA-MM-DD
    cliente           TEXT,
    forma_pagamento   TEXT NOT NULL CHECK (forma_pagamento IN ('pix', 'dinheiro', 'credito', 'debito')),
    recebido_centavos INTEGER NOT NULL,       -- quanto caiu na conta (já sem a taxa da maquininha)
    agendado_por      TEXT,
    evento_id         INTEGER REFERENCES eventos(id),
    descricao         TEXT
);

-- Cada serviço/produto dentro da visita (várias perfurações, joia, etc.)
CREATE TABLE IF NOT EXISTS itens_atendimento (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    atendimento_id INTEGER NOT NULL REFERENCES atendimentos(id) ON DELETE CASCADE,
    categoria_id   INTEGER NOT NULL REFERENCES categorias(id),
    servico_id     INTEGER REFERENCES servicos(id),
    valor_centavos INTEGER NOT NULL           -- preço cobrado do cliente por este item
);

CREATE TABLE IF NOT EXISTS saidas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    data           TEXT NOT NULL,
    categoria_id   INTEGER NOT NULL REFERENCES categorias(id),
    valor_centavos INTEGER NOT NULL,
    descricao      TEXT
);

-- Quem pode entrar no sistema (a senha é guardada só como hash, nunca em texto)
CREATE TABLE IF NOT EXISTS usuarios (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    nome              TEXT NOT NULL UNIQUE,
    senha_hash        TEXT NOT NULL,
    tentativas_falhas INTEGER NOT NULL DEFAULT 0,
    bloqueado_ate     TEXT
);
