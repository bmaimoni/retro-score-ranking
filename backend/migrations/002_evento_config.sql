-- ─────────────────────────────────────────────────────────────────────────────
-- Retro Score Ranking — migração 002
-- Tabela de configuração da página de upload por evento
-- Executar no Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS evento_config (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    chave         text        UNIQUE NOT NULL,  -- ex: "upload_titulo"
    valor         text        NOT NULL,
    descricao     text,                          -- hint para o admin
    atualizado_em timestamptz NOT NULL DEFAULT now()
);

-- Valores padrão da página de upload
INSERT INTO evento_config (chave, valor, descricao) VALUES
    ('upload_titulo',    'INSERT COIN',                        'Título principal da tela de upload'),
    ('upload_subtitulo', 'Fotografe seu placar e entre no ranking', 'Subtítulo da tela de upload'),
    ('upload_botao',     'ENVIAR PONTUAÇÃO',                   'Texto do botão de envio'),
    ('upload_sucesso',   'PONTUAÇÃO REGISTRADA!',              'Mensagem de sucesso após envio'),
    ('evento_nome',      'Retro Score Ranking',                'Nome do evento (aparece no título da aba)'),
    ('evento_ativo',     'true',                               'Habilita ou desabilita envios (true/false)')
ON CONFLICT (chave) DO NOTHING;
