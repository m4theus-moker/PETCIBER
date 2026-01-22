import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "petciber.db")
with sqlite3.connect(DB_PATH) as conn:
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN nome_completo TEXT")
        cursor.execute("ALTER TABLE usuarios ADD COLUMN telefone TEXT")
        conn.commit()
        print("Colunas 'nome_completo' e 'telefone' adicionadas à tabela 'usuarios'.")
    except sqlite3.OperationalError as e:
        print("Aviso:", e)
