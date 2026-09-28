"""
1_extrair.py
------------
FASE 1 - Extracao e camada RAW.

1. Baixa o .zip de Viagens a Servico (Google Drive) para a pasta data/,
   somente se os 4 CSVs ainda nao estiverem la.
2. Le cada CSV em blocos (chunksize), tudo como texto.
3. Carrega cada bloco na tabela RAW correspondente, SEM alterar nenhum valor.

Garantias:
- Idempotente: TRUNCATE antes de cada carga (rodar de novo nao duplica).
- Resiliente: try/except + rollback() (nada fica pela metade).
- INSERT pela POSICAO das colunas (o espaco escondido no nome de uma coluna
  do CSV de trechos nao atrapalha).

Como executar:  python 1_extrair.py
"""

import sys
import time
import zipfile

import pandas as pd
import requests
from psycopg2.extras import execute_values

from banco import conectar
from config import (
    ARQUIVOS,
    CSV_ENCODING,
    CSV_SEPARADOR,
    DRIVE_FILE_ID,
    PASTA_DADOS,
    TAMANHO_BLOCO,
)

URL_DOWNLOAD_DRIVE = "https://drive.usercontent.google.com/download"
ARQUIVO_ZIP = PASTA_DADOS / "viagens_2025_6meses.zip"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def csvs_ja_existem():
    """Retorna True se os 4 CSVs ja estao na pasta data/."""
    return all((PASTA_DADOS / info["csv"]).exists() for info in ARQUIVOS.values())


def baixar_zip():
    """Baixa o .zip do Google Drive em partes (streaming) para data/."""
    if DRIVE_FILE_ID.startswith("COLE_AQUI"):
        raise RuntimeError(
            "Cole o ID do arquivo no DRIVE_FILE_ID (config.py) ou coloque os "
            f"4 CSVs manualmente na pasta {PASTA_DADOS}."
        )

    print("Baixando o arquivo .zip do Google Drive...")
    parametros = {"id": DRIVE_FILE_ID, "export": "download", "confirm": "t"}
    with requests.get(URL_DOWNLOAD_DRIVE, params=parametros,
                      stream=True, timeout=120) as resposta:
        resposta.raise_for_status()
        with open(ARQUIVO_ZIP, "wb") as arquivo:
            for pedaco in resposta.iter_content(chunk_size=1024 * 1024):
                arquivo.write(pedaco)

    # Se o Drive devolver uma pagina HTML (aviso/permissao), nao e um zip.
    if not zipfile.is_zipfile(ARQUIVO_ZIP):
        ARQUIVO_ZIP.unlink(missing_ok=True)
        raise RuntimeError(
            "O download nao retornou um .zip valido. Verifique se o arquivo "
            "no Drive esta compartilhado ou baixe-o manualmente para data/."
        )
    tamanho_mb = ARQUIVO_ZIP.stat().st_size / 1024 / 1024
    print(f"  download concluido ({tamanho_mb:.1f} MB)")


def extrair_zip():
    """Extrai os CSVs do .zip para a pasta data/."""
    with zipfile.ZipFile(ARQUIVO_ZIP) as arquivo_zip:
        for nome in arquivo_zip.namelist():
            if nome.lower().endswith(".csv"):
                # extrai "achatado" (sem subpastas) direto em data/
                destino = PASTA_DADOS / nome.split("/")[-1]
                with arquivo_zip.open(nome) as origem, open(destino, "wb") as saida:
                    saida.write(origem.read())
                print(f"  extraido: {destino.name}")


def garantir_csvs():
    """Garante que os 4 CSVs estao em data/ (baixa e extrai se preciso)."""
    PASTA_DADOS.mkdir(exist_ok=True)
    if csvs_ja_existem():
        print("CSVs ja estao em data/ - download ignorado.")
        return
    if not ARQUIVO_ZIP.exists():
        baixar_zip()
    extrair_zip()
    if not csvs_ja_existem():
        faltando = [i["csv"] for i in ARQUIVOS.values()
                    if not (PASTA_DADOS / i["csv"]).exists()]
        raise RuntimeError(f"CSVs nao encontrados apos extrair o zip: {faltando}")


# ---------------------------------------------------------------------------
# Carga na RAW
# ---------------------------------------------------------------------------
def carregar_raw(conexao, nome_csv, tabela):
    """
    Esvazia a tabela RAW e carrega o CSV em blocos, sem alterar valores.
    Retorna o total de linhas inseridas. O commit fica com quem chama.
    """
    cursor = conexao.cursor()
    cursor.execute(f"TRUNCATE {tabela}")  # nao duplica ao rodar de novo

    total = 0
    blocos = pd.read_csv(
        PASTA_DADOS / nome_csv,
        sep=CSV_SEPARADOR,
        encoding=CSV_ENCODING,
        dtype=str,               # tudo texto: preserva zeros a esquerda
        keep_default_na=False,   # vazio continua vazio (nao vira NaN)
        chunksize=TAMANHO_BLOCO,
    )
    for bloco in blocos:
        linhas = list(bloco.itertuples(index=False, name=None))
        # INSERT pela posicao: nao depende dos nomes das colunas do CSV
        execute_values(cursor, f"INSERT INTO {tabela} VALUES %s", linhas,
                       page_size=5_000)
        total += len(linhas)
        print(f"    {tabela}: {total:,} linhas".replace(",", "."), end="\r")

    cursor.close()
    print()
    return total


def main():
    inicio = time.time()
    try:
        garantir_csvs()
    except Exception as erro:  # noqa: BLE001 - mensagem clara para o usuario
        print(f"ERRO na extracao: {erro}")
        sys.exit(1)

    conexao = conectar()
    try:
        print("\nCarregando a camada RAW...")
        for info in ARQUIVOS.values():
            total = carregar_raw(conexao, info["csv"], info["tabela_raw"])
            conexao.commit()  # confirma cada tabela carregada
            print(f"  OK {info['tabela_raw']}: {total:,} linhas".replace(",", "."))
    except Exception as erro:  # noqa: BLE001
        conexao.rollback()  # desfaz a tabela que estava pela metade
        print(f"ERRO na carga da RAW (rollback executado): {erro}")
        sys.exit(1)
    finally:
        conexao.close()

    print(f"\nCamada RAW pronta em {time.time() - inicio:.0f}s.")


if __name__ == "__main__":
    main()
