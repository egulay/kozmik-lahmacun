\set ON_ERROR_STOP on
SET search_path TO kozmik_lahmacun;

-- Local control-plane identities only. Data entities belong to the separate
-- demo-data seed workflow and must not appear after a clean platform reset.
INSERT INTO app_user_reference
    (id, keycloak_user_id, display_name, email, created_at, updated_at)
VALUES
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
     'Demo Reporter', 'reporter@kozmik.local', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2',
     'Demo Scientist', 'scientist@kozmik.local', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3',
     'Demo Admin', 'admin@kozmik.local', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
