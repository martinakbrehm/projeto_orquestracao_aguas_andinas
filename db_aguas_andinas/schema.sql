-- =============================================================================
-- schema.sql  –  Banco Águas Andinas: bd_Automacoes_time_dados_aguas_andinas
-- =============================================================================
-- Execução: python db_aguas_andinas/setup_database.py
--
-- Estrutura:
--   • clientes          — RUT + DV (identificador chileno, equivalente ao CPF BR)
--   • enderecos         — direccion, comuna, region
--   • lotes             — controle de execuções do pipeline de enriquecimento
--   • telefones         — todos os telefones do cliente; origem identifica a fonte
--   • emails            — todos os e-mails do cliente; origem identifica a fonte
--   • tabela_macros_aa  — controle de execução da macro por cliente (status/resposta)
--   • respostas         — 5 cenários reais de retorno da macro
--   • telefones / emails → staging_id (FK staging_imports) ao invés de lote_id
--
-- origem possíveis (telefones e emails):
--   enriquecimento  → inserido pelo pipeline (base histórica)
--   validado         → confirmado/extraído pela macro/API em tempo de execução
-- =============================================================================

USE `bd_Automacoes_time_dados_aguas_andinas`;

-- ---------------------------------------------------------------------------
-- Respostas da macro Águas Andinas
-- Mapeamento dos cenários reais observados no arquivo de resultado.
--
--   id | mensagem                                   | status
--   ---+--------------------------------------------+------------------------
--    1 | Sucesso com telefone e e-mail               | telefone_validado
--    2 | Sucesso sem dados                           | telefone_nao_validado
--    3 | Usuário já registrado                         | telefone_nao_validado
--    4 | Falha de conexão / API                       | telefone_nao_validado
--    5 | Aguardando processamento                    | telefone_nao_validado
--    6 | Sucesso apenas com telefone                 | telefone_validado
--    7 | Sucesso apenas com e-mail                   | telefone_nao_validado
--    8 | Telefone inválido (normalização)            | telefone_nao_validado
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS respostas (
  id       TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
  mensagem TEXT,
  status   VARCHAR(50) NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO respostas (id, mensagem, status) VALUES
  (1, 'Sucesso com telefone e e-mail',            'telefone_validado'),
  (2, 'Sucesso sem dados',                         'telefone_nao_validado'),
  (3, 'Usuário já registrado',                     'telefone_nao_validado'),
  (4, 'Falha de conexão / API',                   'telefone_nao_validado'),
  (5, 'Aguardando processamento',                 'telefone_nao_validado'),
  (6, 'Sucesso apenas com telefone',              'telefone_validado'),
  (7, 'Sucesso apenas com e-mail',                'telefone_nao_validado'),
  (8, 'Telefone invalido',                          'telefone_nao_validado')
ON DUPLICATE KEY UPDATE mensagem = VALUES(mensagem), status = VALUES(status);


-- ---------------------------------------------------------------------------
-- Clientes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clientes (
  id              INT NOT NULL AUTO_INCREMENT,
  rut             CHAR(8) NOT NULL,           -- RUT sem DV e sem pontos (ex: 12345678)
  dv              CHAR(1) DEFAULT NULL,        -- dígito verificador (0-9 ou K)
  nome            VARCHAR(255) DEFAULT NULL,
  sexo            CHAR(1) DEFAULT NULL,        -- M / F
  data_nascimento DATE DEFAULT NULL,
  data_criacao    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  data_update     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  staging_id      INT DEFAULT NULL,            -- FK → staging_imports (importação de origem)
  PRIMARY KEY (id),
  UNIQUE KEY ux_clientes_rut (rut),
  KEY idx_clientes_staging (staging_id),
  CONSTRAINT fk_clientes_staging FOREIGN KEY (staging_id) REFERENCES staging_imports(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

DELIMITER //
CREATE TRIGGER IF NOT EXISTS before_insert_clientes
BEFORE INSERT ON clientes
FOR EACH ROW
BEGIN
  -- Garante RUT sem zeros à esquerda desnecessários e uppercase do DV
  SET NEW.rut = TRIM(LEADING '0' FROM NEW.rut);
  IF NEW.dv IS NOT NULL THEN
    SET NEW.dv = UPPER(NEW.dv);
  END IF;
END //

CREATE TRIGGER IF NOT EXISTS before_update_clientes
BEFORE UPDATE ON clientes
FOR EACH ROW
BEGIN
  SET NEW.rut = TRIM(LEADING '0' FROM NEW.rut);
  IF NEW.dv IS NOT NULL THEN
    SET NEW.dv = UPPER(NEW.dv);
  END IF;
END //
DELIMITER ;


-- ---------------------------------------------------------------------------
-- Endereços (chilenos)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enderecos (
  id           INT NOT NULL AUTO_INCREMENT,
  cliente_id   INT NOT NULL,
  direccion    VARCHAR(255) DEFAULT NULL,
  comuna       VARCHAR(100) DEFAULT NULL,
  region       VARCHAR(100) DEFAULT NULL,
  data_criacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_enderecos_cliente (cliente_id),
  CONSTRAINT fk_enderecos_cliente FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- Telefones
-- Armazena todos os telefones do cliente, independente da origem.
--   origem = enriquecimento → inserido pelo pipeline (base histórica)
--   origem = validado       → confirmado/extraído pela macro/API
-- Um mesmo número pode estar associado a múltiplos clientes (N:N via cliente_id).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telefones (
  id           INT NOT NULL AUTO_INCREMENT,
  cliente_id   INT NOT NULL,
  numero       VARCHAR(20) NOT NULL,
  origem       ENUM('enriquecimento','validado') NOT NULL DEFAULT 'enriquecimento',
  staging_id   INT DEFAULT NULL,           -- FK staging_imports (preenchido quando origem=enriquecimento)
  data_criacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY ux_telefone_cliente_numero_origem (cliente_id, numero, origem),
  INDEX idx_telefones_cliente  (cliente_id),
  INDEX idx_telefones_numero   (numero),
  INDEX idx_telefones_origem   (origem),
  INDEX idx_telefones_staging  (staging_id),
  CONSTRAINT fk_telefones_cliente  FOREIGN KEY (cliente_id)  REFERENCES clientes(id)        ON DELETE CASCADE,
  CONSTRAINT fk_telefones_staging  FOREIGN KEY (staging_id)  REFERENCES staging_imports(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- Emails
-- Armazena todos os e-mails do cliente, independente da origem.
--   origem = enriquecimento → inserido pelo pipeline (base histórica)
--   origem = validado       → confirmado/extraído pela macro/API
-- Um mesmo endereço pode estar associado a múltiplos clientes (N:N via cliente_id).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS emails (
  id           INT NOT NULL AUTO_INCREMENT,
  cliente_id   INT NOT NULL,
  endereco     VARCHAR(255) NOT NULL,
  origem       ENUM('enriquecimento','validado') NOT NULL DEFAULT 'enriquecimento',
  staging_id   INT DEFAULT NULL,           -- FK staging_imports (preenchido quando origem=enriquecimento)
  data_criacao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY ux_email_cliente_endereco_origem (cliente_id, endereco, origem),
  INDEX idx_emails_cliente   (cliente_id),
  INDEX idx_emails_endereco  (endereco),
  INDEX idx_emails_origem    (origem),
  INDEX idx_emails_staging   (staging_id),
  CONSTRAINT fk_emails_cliente  FOREIGN KEY (cliente_id)  REFERENCES clientes(id)        ON DELETE CASCADE,
  CONSTRAINT fk_emails_staging  FOREIGN KEY (staging_id)  REFERENCES staging_imports(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- Tabela de controle da macro Águas Andinas
--
-- Regras de negócio:
--   • 1 registro por cliente (UNIQUE KEY em cliente_id)
--   • A macro atualiza: resposta_id, status, data_update
--   • A macro NÃO toca: extraido, data_extracao
--
-- telefone_id / email_id → FK para o registro inserido em
--                          telefones / emails (origem=validado)
--
-- Status possíveis:
--   pendente                → ainda não processado (ou falha → retentar)
--   processando             → em andamento
--   telefone_validado       → SUCESSO=1 e retornou telefone (com ou sem e-mail)
--   telefone_nao_validado   → SUCESSO=1 sem telefone, ou usuário registrado
--
-- Controle de extração (extraido / data_extracao):
--   extraido = 0, data_extracao = NULL  → padrão ao inserir; dado ainda não consumido
--   extraido = 1, data_extracao = <dt>  → dado já consumido em alguma ação/envio
--   Esses campos são gerenciados manualmente — nunca pela macro/ETL.
--   Uso típico para evitar reuso: WHERE extraido = 0 AND status = 'telefone_validado'
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tabela_macros_aa (
  id             INT NOT NULL AUTO_INCREMENT,
  cliente_id     INT NOT NULL,
  resposta_id    TINYINT UNSIGNED DEFAULT 5,   -- default: pendente (id=5)
  telefone_id    INT DEFAULT NULL,              -- FK → telefones (origem=validado)
  email_id       INT DEFAULT NULL,              -- FK → emails    (origem=validado)
  status         ENUM('pendente','processando','telefone_validado','telefone_nao_validado')
                 NOT NULL DEFAULT 'pendente',
  extraido       TINYINT(1) NOT NULL DEFAULT 0,         -- 0=não consumido, 1=já usado
  data_extracao  DATETIME DEFAULT NULL,                  -- data em que foi consumido
  data_criacao   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  data_update    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_aa_macros_cliente (cliente_id),
  CONSTRAINT fk_aa_macros_cliente  FOREIGN KEY (cliente_id)  REFERENCES clientes(id)  ON DELETE CASCADE,
  CONSTRAINT fk_aa_macros_resposta FOREIGN KEY (resposta_id) REFERENCES respostas(id) ON DELETE SET NULL,
  CONSTRAINT fk_aa_macros_telefone FOREIGN KEY (telefone_id) REFERENCES telefones(id) ON DELETE SET NULL,
  CONSTRAINT fk_aa_macros_email    FOREIGN KEY (email_id)    REFERENCES emails(id)    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE tabela_macros_aa
  ADD INDEX idx_aa_macros_status_data  (status, data_update, cliente_id),
  ADD INDEX idx_aa_macros_cliente_data (cliente_id, data_update),
  ADD INDEX idx_aa_macros_resposta     (resposta_id),
  ADD INDEX idx_aa_macros_telefone     (telefone_id),
  ADD INDEX idx_aa_macros_email        (email_id),
  ADD INDEX idx_aa_macros_extraido     (extraido);


-- ---------------------------------------------------------------------------
-- Staging — importação de arquivos CSV
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging_imports (
  id                 INT NOT NULL AUTO_INCREMENT,
  filename           VARCHAR(255) NOT NULL,
  total_rows         INT DEFAULT 0,
  rows_success       INT DEFAULT 0,
  rows_failed        INT DEFAULT 0,
  status             ENUM('pending','processing','completed','failed') NOT NULL DEFAULT 'pending',
  imported_by        VARCHAR(100) DEFAULT NULL,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at         DATETIME DEFAULT NULL,
  finished_at        DATETIME DEFAULT NULL,
  PRIMARY KEY (id),
  INDEX idx_staging_status     (status),
  INDEX idx_staging_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS staging_import_rows (
  id                 INT NOT NULL AUTO_INCREMENT,
  staging_id         INT NOT NULL,
  row_idx            INT DEFAULT NULL,
  raw_rut            VARCHAR(50) DEFAULT NULL,
  raw_nome           VARCHAR(255) DEFAULT NULL,
  normalized_rut     CHAR(8) DEFAULT NULL,
  normalized_dv      CHAR(1) DEFAULT NULL,
  validation_status  ENUM('new','valid','invalid','skipped') DEFAULT 'new',
  validation_message VARCHAR(255) DEFAULT NULL,
  processed_at       DATETIME DEFAULT NULL,
  PRIMARY KEY (id),
  INDEX idx_staging_rows_staging    (staging_id),
  INDEX idx_staging_rows_normrut    (normalized_rut),
  CONSTRAINT fk_staging_rows_imports FOREIGN KEY (staging_id) REFERENCES staging_imports(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------

-- Macro: pendentes de execução (mais recente por RUT)
CREATE OR REPLACE VIEW view_aa_macros_pendentes AS
SELECT vm.*
FROM (
  SELECT
    tm.*,
    c.rut AS __rut,
    ROW_NUMBER() OVER (
      PARTITION BY c.rut
      ORDER BY tm.data_update DESC, tm.id DESC
    ) AS rn
  FROM tabela_macros_aa tm
  JOIN clientes c ON c.id = tm.cliente_id
  WHERE tm.status = 'pendente'
) vm
WHERE vm.rn = 1;

-- Macro: ativos com dados extraídos (join com telefones/emails)
CREATE OR REPLACE VIEW view_aa_macros_ativos AS
SELECT
  tm.id,
  c.rut,
  c.dv,
  c.nome,
  t.numero   AS telefone_extraido,
  e.endereco AS email_extraido,
  tm.status,
  tm.data_criacao,
  tm.data_update
FROM tabela_macros_aa tm
JOIN  clientes  c ON c.id = tm.cliente_id
LEFT JOIN telefones t ON t.id = tm.telefone_id
LEFT JOIN emails    e ON e.id = tm.email_id
WHERE tm.status IN ('telefone_validado', 'telefone_nao_validado');

-- Consolidado por cliente: todos os contatos por origem
CREATE OR REPLACE VIEW view_aa_clientes_contatos AS
SELECT
  c.id        AS cliente_id,
  c.rut,
  c.dv,
  c.nome,
  c.sexo,
  c.data_nascimento,
  en.direccion,
  en.comuna,
  en.region,
  t.numero    AS telefone,
  t.origem    AS telefone_origem,   -- 'enriquecimento' | 'validado'
  em.endereco AS email,
  em.origem   AS email_origem       -- 'enriquecimento' | 'validado'
FROM clientes c
LEFT JOIN enderecos en ON en.cliente_id = c.id
LEFT JOIN telefones t  ON t.cliente_id  = c.id
LEFT JOIN emails    em ON em.cliente_id = c.id;


-- ---------------------------------------------------------------------------
-- Stored procedures
-- ---------------------------------------------------------------------------
DELIMITER $$

CREATE PROCEDURE get_aa_macros_batch(IN batch_size INT)
BEGIN
  IF batch_size IS NULL OR batch_size <= 0 THEN
    SET batch_size = 2000;
  END IF;
  SELECT * FROM view_aa_macros_pendentes
  ORDER BY data_update ASC, id ASC
  LIMIT batch_size;
END$$

DELIMITER ;

-- ---------------------------------------------------------------------------
-- Tabelas materializadas — Dashboard analítico
--
-- Populadas pela procedure sp_refresh_dashboard_agg().
-- O loader (dashboard_macros/data/loader.py) lê exclusivamente dessas
-- tabelas; nenhuma query pesada é feita em tempo de request.
--
-- Refresh:
--   • Automático: 08h e 17h via thread interna do dashboard
--   • Manual:     CALL sp_refresh_dashboard_agg()
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dashboard_macros_agg (
  dia           DATE,
  status        VARCHAR(50),
  mensagem      TEXT,
  qtd           INT,
  atualizado_em DATETIME,
  KEY idx_dma_dia    (dia),
  KEY idx_dma_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Agrega resultados por dia/status/mensagem (tabela materializada)';

CREATE TABLE IF NOT EXISTS dashboard_status_agg (
  status        VARCHAR(50),
  qtd           INT,
  atualizado_em DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Distribuição total de status (tabela materializada)';

CREATE TABLE IF NOT EXISTS dashboard_staging_agg (
  arquivo           VARCHAR(255),
  data_carga        DATE,
  clientes_no_banco INT,
  processados       INT,
  pendentes         INT,
  com_telefone      INT,
  sem_telefone      INT,
  atualizado_em     DATETIME,
  KEY idx_dsa_arquivo (arquivo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Estatísticas por arquivo de staging (tabela materializada)';


-- ---------------------------------------------------------------------------
-- Procedure de refresh das tabelas materializadas
-- ---------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_refresh_dashboard_agg$$

CREATE PROCEDURE sp_refresh_dashboard_agg()
BEGIN
  DECLARE v_now DATETIME DEFAULT NOW();

  -- Agrega resultados por dia / status / mensagem de resposta
  TRUNCATE TABLE dashboard_macros_agg;
  INSERT INTO dashboard_macros_agg (dia, status, mensagem, qtd, atualizado_em)
    SELECT
      DATE(tm.data_update),
      tm.status,
      r.mensagem,
      COUNT(*),
      v_now
    FROM tabela_macros_aa tm
    LEFT JOIN respostas r ON r.id = tm.resposta_id
    WHERE tm.status NOT IN ('pendente', 'processando')
    GROUP BY DATE(tm.data_update), tm.status, r.mensagem
    ORDER BY DATE(tm.data_update) DESC;

  -- Distribuição total por status
  TRUNCATE TABLE dashboard_status_agg;
  INSERT INTO dashboard_status_agg (status, qtd, atualizado_em)
    SELECT tm.status, COUNT(*), v_now
    FROM tabela_macros_aa tm
    GROUP BY tm.status
    ORDER BY COUNT(*) DESC;

  -- Estatísticas por arquivo de staging
  TRUNCATE TABLE dashboard_staging_agg;
  INSERT INTO dashboard_staging_agg
    (arquivo, data_carga, clientes_no_banco, processados, pendentes, com_telefone, sem_telefone, atualizado_em)
    SELECT
      si.filename,
      DATE(si.created_at),
      COUNT(DISTINCT c.id),
      SUM(IF(tm.status NOT IN ('pendente','processando'), 1, 0)),
      SUM(IF(tm.status = 'pendente', 1, 0)),
      SUM(IF(tm.status = 'telefone_validado', 1, 0)),
      SUM(IF(tm.status = 'telefone_nao_validado', 1, 0)),
      v_now
    FROM staging_imports si
    JOIN clientes c ON c.staging_id = si.id
    JOIN tabela_macros_aa tm ON tm.cliente_id = c.id
    WHERE si.status = 'completed'
    GROUP BY si.id, si.filename, si.created_at, si.rows_success
    ORDER BY si.created_at DESC;
END$$

DELIMITER ;

-- =============================================================================
-- FIM DO SCHEMA
-- =============================================================================
