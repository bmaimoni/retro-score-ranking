-- ─────────────────────────────────────────────────────────────────────────────
-- Retro Score Ranking — migração 005
-- Adiciona configurações de rate limit na tabela evento_config
-- Executar no Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO evento_config (chave, valor, descricao) VALUES
    ('rate_limit',        '10', 'Máximo de uploads por IP por hora antes de ir para moderação'),
    ('rate_window_horas', '1',  'Janela de tempo do rate limit em horas')
ON CONFLICT (chave) DO NOTHING;
