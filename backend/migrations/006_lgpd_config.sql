-- ─────────────────────────────────────────────────────────────────────────────
-- Retro Score Ranking — migração 006
-- Adiciona texto LGPD configurável pelo painel admin
-- Executar no Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO evento_config (chave, valor, descricao) VALUES
    ('lgpd_texto',
     'Concordo que minha foto, nome e pontuação sejam exibidos no ranking público e armazenados pelo Canal3. Os dados poderão ser mantidos após o encerramento do evento para fins de histórico e divulgação.',
     'Texto do consentimento LGPD exibido no formulário de upload')
ON CONFLICT (chave) DO NOTHING;
