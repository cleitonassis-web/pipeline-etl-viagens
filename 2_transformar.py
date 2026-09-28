"""
2_transformar.py
----------------
FASE 2 - Transformacao: RAW -> SILVER.

- Le cada tabela RAW em blocos (cursor do lado do servidor).
- Limpa textos e converte tipos com funcoes especificas:
    texto_para_decimal  "1272,97"    -> 1272.97
    texto_para_data     "17/09/2024" -> data
    limpar_texto        " Aereo "    -> "Aereo" (vazio vira NULL)
- Calcula as colunas valor_total e duracao_dias (silver_viagem).
- Respeita a integridade referencial: a mae (silver_viagem) e carregada
  antes das filhas (pagamento, passagem, trecho).
- Idempotente: TRUNCATE das 4 tabelas Silver no mesmo comando.
- Resiliente: try/except + rollback().
- Termina com a CONFERENCIA Raw x Silver (prova de que nada se perdeu).

Como executar:  python 2_transformar.py
"""

import sys
import time

import pandas as pd
from psycopg2.extras import execute_values

from banco import conectar
from config import TAMANHO_BLOCO

VALOR_NAO_INFORMADO = "NAO INFORMADO"


# ---------------------------------------------------------------------------
# Funcoes de conversao (tratamento de dados)
# ---------------------------------------------------------------------------
def limpar_texto(coluna, tamanho_maximo=None):
    """
    ' Aereo ' -> 'Aereo'. Texto vazio vira None (NULL no banco).
    Se 'tamanho_maximo' for informado, corta o texto no tamanho da coluna.
    """
    coluna = coluna.fillna("").astype(str).str.strip()
    if tamanho_maximo:
        coluna = coluna.str.slice(0, tamanho_maximo)
    return coluna.where(coluna != "", None)


def texto_para_decimal(coluna):
    """'1272,97' -> 1272.97. Texto vazio ou invalido vira NaN."""
    coluna = coluna.fillna("").astype(str).str.strip()
    coluna = coluna.str.replace(",", ".", regex=False)  # virgula decimal
    return pd.to_numeric(coluna, errors="coerce")


def texto_para_data(coluna):
    """'17/09/2024' -> data. Texto vazio ou invalido vira NaT."""
    coluna = coluna.fillna("").astype(str).str.strip()
    return pd.to_datetime(coluna, format="%d/%m/%Y", errors="coerce").dt.date


def texto_para_inteiro(coluna):
    """'3' -> 3. Texto vazio ou invalido vira <NA>."""
    return pd.to_numeric(texto_para_decimal(coluna), errors="coerce").astype("Int64")


def preencher_obrigatorio(coluna):
    """Colunas NOT NULL: vazio vira 'NAO INFORMADO' (decisao documentada)."""
    return coluna.where(coluna.notna(), VALOR_NAO_INFORMADO)


def para_banco(df):
    """NaN, NaT e <NA> viram None, que o banco grava como NULL."""
    df = df.astype(object)
    return df.where(pd.notna(df), None)


# ---------------------------------------------------------------------------
# Transformacao de cada tabela (recebe um bloco da RAW, devolve a Silver)
# ---------------------------------------------------------------------------
def transformar_viagem(raw):
    silver = pd.DataFrame({
        "id_viagem": limpar_texto(raw["id_viagem"], 20),
        "num_proposta": limpar_texto(raw["num_proposta"], 20),
        "situacao": limpar_texto(raw["situacao"], 50),
        "viagem_urgente": limpar_texto(raw["viagem_urgente"], 5),
        "cod_orgao_superior": limpar_texto(raw["cod_orgao_superior"], 20),
        "nome_orgao_superior": preencher_obrigatorio(
            limpar_texto(raw["nome_orgao_superior"], 255)),
        "nome_viajante": limpar_texto(raw["nome_viajante"], 255),
        "cargo": limpar_texto(raw["cargo"], 255),
        "data_inicio": texto_para_data(raw["data_inicio"]),
        "data_fim": texto_para_data(raw["data_fim"]),
        "destinos": limpar_texto(raw["destinos"], 4000),
        "motivo": limpar_texto(raw["motivo"], 4000),
        "valor_diarias": texto_para_decimal(raw["valor_diarias"]),
        "valor_passagens": texto_para_decimal(raw["valor_passagens"]),
        "valor_devolucao": texto_para_decimal(raw["valor_devolucao"]),
        "valor_outros_gastos": texto_para_decimal(raw["valor_outros_gastos"]),
    })

    # valor_total = diarias + passagens + outros gastos - devolucao
    silver["valor_total"] = (
        silver["valor_diarias"].fillna(0)
        + silver["valor_passagens"].fillna(0)
        + silver["valor_outros_gastos"].fillna(0)
        - silver["valor_devolucao"].fillna(0)
    ).round(2)

    # duracao_dias = (data_fim - data_inicio) + 1  (inclui o dia de saida)
    inicio = pd.to_datetime(silver["data_inicio"])
    fim = pd.to_datetime(silver["data_fim"])
    silver["duracao_dias"] = ((fim - inicio).dt.days + 1).astype("Int64")
    return silver


def transformar_pagamento(raw):
    return pd.DataFrame({
        "id_viagem": limpar_texto(raw["id_viagem"], 20),
        "num_proposta": limpar_texto(raw["num_proposta"], 20),
        "nome_orgao_pagador": limpar_texto(raw["nome_orgao_pagador"], 255),
        "nome_ug_pagadora": limpar_texto(raw["nome_ug_pagadora"], 255),
        "tipo_pagamento": preencher_obrigatorio(
            limpar_texto(raw["tipo_pagamento"], 50)),
        "valor": texto_para_decimal(raw["valor"]),
    })


def transformar_passagem(raw):
    return pd.DataFrame({
        "id_viagem": limpar_texto(raw["id_viagem"], 20),
        "meio_transporte": limpar_texto(raw["meio_transporte"], 50),
        "pais_origem_ida": limpar_texto(raw["pais_origem_ida"], 60),
        "uf_origem_ida": limpar_texto(raw["uf_origem_ida"], 40),
        "cidade_origem_ida": limpar_texto(raw["cidade_origem_ida"], 80),
        "pais_destino_ida": limpar_texto(raw["pais_destino_ida"], 60),
        "uf_destino_ida": limpar_texto(raw["uf_destino_ida"], 40),
        "cidade_destino_ida": limpar_texto(raw["cidade_destino_ida"], 80),
        "valor_passagem": texto_para_decimal(raw["valor_passagem"]),
        "taxa_servico": texto_para_decimal(raw["taxa_servico"]),
        "data_emissao": texto_para_data(raw["data_emissao"]),
    })


def transformar_trecho(raw):
    return pd.DataFrame({
        "id_viagem": limpar_texto(raw["id_viagem"], 20),
        "sequencia_trecho": texto_para_inteiro(raw["sequencia_trecho"]),
        "origem_data": texto_para_data(raw["origem_data"]),
        "origem_uf": limpar_texto(raw["origem_uf"], 40),
        "origem_cidade": limpar_texto(raw["origem_cidade"], 80),
        "destino_data": texto_para_data(raw["destino_data"]),
        "destino_uf": limpar_texto(raw["destino_uf"], 40),
        "destino_cidade": limpar_texto(raw["destino_cidade"], 80),
        "meio_transporte": limpar_texto(raw["meio_transporte"], 50),
        "numero_diarias": texto_para_decimal(raw["numero_diarias"]),
    })


# Ordem de carga: a MAE primeiro, depois as filhas (FOREIGN KEY)
ETAPAS = [
    ("raw_viagem", "silver_viagem", transformar_viagem),
    ("raw_pagamento", "silver_pagamento", transformar_pagamento),
    ("raw_passagem", "silver_passagem", transformar_passagem),
    ("raw_trecho", "silver_trecho", transformar_trecho),
]


# ---------------------------------------------------------------------------
# Execucao
# ---------------------------------------------------------------------------
def ler_raw_em_blocos(conexao, tabela):
    """Le a tabela RAW em blocos com um cursor do lado do servidor."""
    cursor = conexao.cursor(name=f"leitura_{tabela}")  # server-side cursor
    cursor.itersize = TAMANHO_BLOCO
    cursor.execute(f"SELECT * FROM {tabela}")
    colunas = None
    while True:
        linhas = cursor.fetchmany(TAMANHO_BLOCO)
        if colunas is None:
            colunas = [desc[0] for desc in cursor.description]
        if not linhas:
            break
        yield pd.DataFrame(linhas, columns=colunas, dtype=str)
    cursor.close()


def carregar_silver(conexao, tabela_raw, tabela_silver, transformar):
    """Transforma a RAW em blocos e insere na Silver. Retorna o total."""
    escrita = conexao.cursor()  # mesma conexao/transacao: tudo ou nada
    total = 0
    for bloco_raw in ler_raw_em_blocos(conexao, tabela_raw):
        bloco = para_banco(transformar(bloco_raw))
        colunas = ", ".join(bloco.columns)
        linhas = list(bloco.itertuples(index=False, name=None))
        execute_values(
            escrita,
            f"INSERT INTO {tabela_silver} ({colunas}) VALUES %s",
            linhas,
            page_size=5_000,
        )
        total += len(linhas)
        print(f"    {tabela_silver}: {total:,} linhas".replace(",", "."), end="\r")
    escrita.close()
    print()
    return total


def consultar_valor(conexao, sql):
    cursor = conexao.cursor()
    cursor.execute(sql)
    valor = cursor.fetchone()[0]
    cursor.close()
    return valor


def formatar(numero):
    """1234567.8 -> '1.234.567,80' (inteiros ficam sem casas decimais)."""
    casas = 0 if float(numero).is_integer() and "." not in str(numero) else 2
    texto = f"{numero:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def conferencia(conexao):
    """Compara Raw x Silver: contagens, datas vazias e soma dos pagamentos."""
    verificacoes = [
        ("linhas de viagem",
         "SELECT COUNT(*) FROM raw_viagem",
         "SELECT COUNT(*) FROM silver_viagem"),
        ("linhas de pagamento",
         "SELECT COUNT(*) FROM raw_pagamento",
         "SELECT COUNT(*) FROM silver_pagamento"),
        ("linhas de passagem",
         "SELECT COUNT(*) FROM raw_passagem",
         "SELECT COUNT(*) FROM silver_passagem"),
        ("linhas de trecho",
         "SELECT COUNT(*) FROM raw_trecho",
         "SELECT COUNT(*) FROM silver_trecho"),
        ("datas de emissao vazias -> NULL",
         "SELECT COUNT(*) FROM raw_passagem WHERE TRIM(data_emissao) = ''",
         "SELECT COUNT(*) FROM silver_passagem WHERE data_emissao IS NULL"),
        ("soma dos pagamentos (R$)",
         "SELECT COALESCE(SUM(REPLACE(NULLIF(TRIM(valor), ''), ',', '.')"
         "::NUMERIC), 0) FROM raw_pagamento",
         "SELECT COALESCE(SUM(valor), 0) FROM silver_pagamento"),
    ]
    print("\nCONFERENCIA RAW x SILVER")
    print(f"{'conferencia':<34}{'raw':>20}{'silver':>20}  resultado")
    tudo_ok = True
    for nome, sql_raw, sql_silver in verificacoes:
        valor_raw = consultar_valor(conexao, sql_raw)
        valor_silver = consultar_valor(conexao, sql_silver)
        ok = valor_raw == valor_silver
        tudo_ok = tudo_ok and ok
        print(f"{nome:<34}{formatar(valor_raw):>20}{formatar(valor_silver):>20}  "
              f"{'OK' if ok else 'DIVERGENTE'}")

    preenchidos = consultar_valor(
        conexao,
        "SELECT (SELECT COUNT(*) FROM silver_viagem "
        f"WHERE nome_orgao_superior = '{VALOR_NAO_INFORMADO}') + "
        "(SELECT COUNT(*) FROM silver_pagamento "
        f"WHERE tipo_pagamento = '{VALOR_NAO_INFORMADO}')",
    )
    print(f"\nCampos obrigatorios preenchidos com '{VALOR_NAO_INFORMADO}': "
          f"{preenchidos}")
    return tudo_ok


def main():
    inicio = time.time()
    conexao = conectar()
    try:
        # Esvazia as 4 tabelas no MESMO comando (as filhas apontam para a mae)
        cursor = conexao.cursor()
        cursor.execute(
            "TRUNCATE silver_pagamento, silver_passagem, silver_trecho, "
            "silver_viagem RESTART IDENTITY"
        )
        cursor.close()

        print("Transformando RAW -> SILVER...")
        for tabela_raw, tabela_silver, transformar in ETAPAS:
            total = carregar_silver(conexao, tabela_raw, tabela_silver, transformar)
            print(f"  OK {tabela_silver}: {total:,} linhas".replace(",", "."))
        conexao.commit()  # so confirma se as 4 tabelas deram certo
    except Exception as erro:  # noqa: BLE001
        conexao.rollback()
        print(f"ERRO na transformacao (rollback executado): {erro}")
        conexao.close()
        sys.exit(1)

    tudo_ok = conferencia(conexao)
    conexao.close()
    print(f"\nCamada SILVER pronta em {time.time() - inicio:.0f}s. "
          f"Conferencia: {'OK' if tudo_ok else 'COM DIVERGENCIAS'}")


if __name__ == "__main__":
    main()
