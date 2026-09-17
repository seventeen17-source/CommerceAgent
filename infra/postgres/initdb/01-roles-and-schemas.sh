#!/bin/bash
# CommerceAgent — 数据库初始化：角色、schema、授权
#
# 执行时机：仅在数据卷为空时，由 postgres 官方镜像的 entrypoint 执行一次。
#
# 职责边界（重要）：
#   本脚本只创建【角色 + schema + 权限】，不创建任何业务表。
#   表的权威是 Flyway（commerce-backend/src/main/resources/db/migration），
#   见 specs/002-commerce-after-sales-agent/research.md 决策 18。
#
# 权限模型：
#   commerce_app  → 拥有 commerce schema                        （Java）
#   agent_app     → 拥有 agent / policy schema                  （Python）
#   migrator      → 可在三个 schema 建对象                      （Flyway）
#   关键约束：agent_app 对 commerce.* 必须无任何权限 —— 这条边界由数据库强制，
#   而不是靠"大家记得别访问"。验证方式：
#     psql -U agent_app -d commerceagent -c 'select * from commerce.orders'
#     期望：permission denied for schema commerce

set -Eeuo pipefail

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v commerce_user="$COMMERCE_APP_USER" \
     -v commerce_pw="$COMMERCE_APP_PASSWORD" \
     -v agent_user="$AGENT_APP_USER" \
     -v agent_pw="$AGENT_APP_PASSWORD" \
     -v migrator_user="$MIGRATOR_USER" \
     -v migrator_pw="$MIGRATOR_PASSWORD" <<-'EOSQL'

    -- 1) 角色（应用角色一律 NOCREATEDB / NOCREATEROLE / NOSUPERUSER）
    CREATE ROLE :"commerce_user" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'commerce_pw';
    CREATE ROLE :"agent_user"    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'agent_pw';
    CREATE ROLE :"migrator_user" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'migrator_pw';

    -- 2) schema：owner 即语义归属
    CREATE SCHEMA commerce AUTHORIZATION :"commerce_user";
    CREATE SCHEMA agent    AUTHORIZATION :"agent_user";
    CREATE SCHEMA policy   AUTHORIZATION :"agent_user";

    -- 3) 边界：收回 PUBLIC 的一切，并显式拒绝 agent 角色进入 commerce
    REVOKE ALL ON SCHEMA commerce FROM PUBLIC;
    REVOKE ALL ON SCHEMA commerce FROM :"agent_user";
    REVOKE ALL ON SCHEMA agent    FROM PUBLIC;
    REVOKE ALL ON SCHEMA policy   FROM PUBLIC;

    -- 4) migrator：可建对象，并有权把对象授权给两个应用角色
    GRANT USAGE, CREATE ON SCHEMA commerce TO :"migrator_user";
    GRANT USAGE, CREATE ON SCHEMA agent    TO :"migrator_user";
    GRANT USAGE, CREATE ON SCHEMA policy   TO :"migrator_user";
    GRANT :"commerce_user" TO :"migrator_user" WITH ADMIN OPTION;
    GRANT :"agent_user"    TO :"migrator_user" WITH ADMIN OPTION;

    -- 5) 应用角色对自己 schema 的权限
    GRANT USAGE, CREATE ON SCHEMA agent  TO :"agent_user";
    GRANT USAGE, CREATE ON SCHEMA policy TO :"agent_user";

    -- 6) pgvector：只在 policy schema 启用，且暂不建任何向量表（US6 才使用）
    CREATE EXTENSION IF NOT EXISTS vector SCHEMA policy;

    -- 7) 默认权限：migrator 之后建的表/序列，自动授权给对应应用角色
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA commerce
        GRANT ALL ON TABLES TO :"commerce_user";
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA commerce
        GRANT ALL ON SEQUENCES TO :"commerce_user";
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA agent
        GRANT ALL ON TABLES TO :"agent_user";
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA agent
        GRANT ALL ON SEQUENCES TO :"agent_user";
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA policy
        GRANT ALL ON TABLES TO :"agent_user";
    ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator_user" IN SCHEMA policy
        GRANT ALL ON SEQUENCES TO :"agent_user";

EOSQL
