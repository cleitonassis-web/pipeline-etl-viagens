-- ===========================================================================
-- 0_criar_banco.sql
-- Pipeline ETL - Viagens a Servico (Portal da Transparencia, jan-jun/2025)
-- Cria o banco "transparencia" e as 8 tabelas: 4 RAW + 4 SILVER.
--
-- O script tem DUAS PARTES:
--   PARTE 1 -> rodar conectado no banco "postgres" (cria o database).
--   PARTE 2 -> rodar conectado no banco "transparencia" (cria as tabelas).
--
-- No psql, basta rodar o arquivo inteiro: o comando \c troca a conexao.
--     psql -U postgres -f 0_criar_banco.sql
-- No pgAdmin/DBeaver: rode a PARTE 1, troque a conexao para "transparencia"
-- e rode a PARTE 2 (a partir da linha "PARTE 2").
-- ===========================================================================


-- ===========================================================================
-- PARTE 1 - banco de dados (conectado em "postgres")
-- Se o banco ja existir, o PostgreSQL avisa com erro e segue para a Parte 2.
-- ===========================================================================
CREATE DATABASE transparencia ENCODING 'UTF8';

\c transparencia


-- ===========================================================================
-- PARTE 2 - tabelas (conectado em "transparencia")
-- Comeca apagando as tabelas antigas: o script pode rodar de novo.
-- As filhas sao apagadas antes da mae por causa das FOREIGN KEYs, e as
-- views/tabelas Gold (criadas pelo 3_analise.ipynb) antes da Silver.
-- ===========================================================================
DROP VIEW IF EXISTS vw_gold_pagamento_resumo;
DROP VIEW IF EXISTS vw_gold_trecho_resumo;
DROP TABLE IF EXISTS gold_pagamento_resumo;
DROP TABLE IF EXISTS gold_trecho_resumo;

DROP TABLE IF EXISTS silver_pagamento;
DROP TABLE IF EXISTS silver_passagem;
DROP TABLE IF EXISTS silver_trecho;
DROP TABLE IF EXISTS silver_viagem;

DROP TABLE IF EXISTS raw_viagem;
DROP TABLE IF EXISTS raw_pagamento;
DROP TABLE IF EXISTS raw_passagem;
DROP TABLE IF EXISTS raw_trecho;


-- ---------------------------------------------------------------------------
-- CAMADA RAW: copia fiel dos CSVs.
-- Todas as colunas VARCHAR, sem chaves e sem constraints.
-- As colunas estao NA MESMA ORDEM do CSV (a carga e feita pela posicao).
-- ---------------------------------------------------------------------------

-- 2025_Viagem.csv (22 colunas)
CREATE TABLE raw_viagem (
    id_viagem                   VARCHAR(50),
    num_proposta                VARCHAR(50),
    situacao                    VARCHAR(100),
    viagem_urgente              VARCHAR(20),
    justificativa_urgencia      VARCHAR(4000),
    cod_orgao_superior          VARCHAR(50),
    nome_orgao_superior         VARCHAR(255),
    cod_orgao_solicitante       VARCHAR(50),
    nome_orgao_solicitante      VARCHAR(255),
    cpf_viajante                VARCHAR(50),
    nome_viajante               VARCHAR(255),
    cargo                       VARCHAR(255),
    funcao                      VARCHAR(255),
    descricao_funcao            VARCHAR(255),
    data_inicio                 VARCHAR(20),
    data_fim                    VARCHAR(20),
    destinos                    VARCHAR(4000),
    motivo                      VARCHAR(4000),
    valor_diarias               VARCHAR(50),
    valor_passagens             VARCHAR(50),
    valor_devolucao             VARCHAR(50),
    valor_outros_gastos         VARCHAR(50)
);

-- 2025_Pagamento.csv (10 colunas)
CREATE TABLE raw_pagamento (
    id_viagem                   VARCHAR(50),
    num_proposta                VARCHAR(50),
    cod_orgao_superior          VARCHAR(50),
    nome_orgao_superior         VARCHAR(255),
    cod_orgao_pagador           VARCHAR(50),
    nome_orgao_pagador          VARCHAR(255),
    cod_ug_pagadora             VARCHAR(50),
    nome_ug_pagadora            VARCHAR(255),
    tipo_pagamento              VARCHAR(100),
    valor                       VARCHAR(50)
);

-- 2025_Passagem.csv (19 colunas)
CREATE TABLE raw_passagem (
    id_viagem                   VARCHAR(50),
    num_proposta                VARCHAR(50),
    meio_transporte             VARCHAR(100),
    pais_origem_ida             VARCHAR(100),
    uf_origem_ida               VARCHAR(100),
    cidade_origem_ida           VARCHAR(150),
    pais_destino_ida            VARCHAR(100),
    uf_destino_ida              VARCHAR(100),
    cidade_destino_ida          VARCHAR(150),
    pais_origem_volta           VARCHAR(100),
    uf_origem_volta             VARCHAR(100),
    cidade_origem_volta         VARCHAR(150),
    pais_destino_volta          VARCHAR(100),
    uf_destino_volta            VARCHAR(100),
    cidade_destino_volta        VARCHAR(150),
    valor_passagem              VARCHAR(50),
    taxa_servico                VARCHAR(50),
    data_emissao                VARCHAR(20),
    hora_emissao                VARCHAR(20)
);

-- 2025_Trecho.csv (14 colunas)
CREATE TABLE raw_trecho (
    id_viagem                   VARCHAR(50),
    num_proposta                VARCHAR(50),
    sequencia_trecho            VARCHAR(20),
    origem_data                 VARCHAR(20),
    origem_pais                 VARCHAR(100),
    origem_uf                   VARCHAR(100),
    origem_cidade               VARCHAR(150),
    destino_data                VARCHAR(20),
    destino_pais                VARCHAR(100),
    destino_uf                  VARCHAR(100),
    destino_cidade              VARCHAR(150),
    meio_transporte             VARCHAR(100),
    numero_diarias              VARCHAR(50),
    missao                      VARCHAR(20)
);
