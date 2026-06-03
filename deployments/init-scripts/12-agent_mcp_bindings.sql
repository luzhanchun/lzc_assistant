/*
 Agent MCP Bindings Migration

 Binds user-defined MCP servers to one or more registered agents.
*/

CREATE TABLE IF NOT EXISTS "public"."agent_mcp_bindings" (
  "id" uuid NOT NULL DEFAULT uuid_generate_v4(),
  "user_id" varchar(255) COLLATE "pg_catalog"."default" NOT NULL,
  "agent_name" varchar(100) COLLATE "pg_catalog"."default" NOT NULL,
  "mcp_server_name" varchar(128) COLLATE "pg_catalog"."default" NOT NULL,
  "created_at" timestamp(6) NOT NULL DEFAULT now(),
  "updated_at" timestamp(6) NOT NULL DEFAULT now(),
  CONSTRAINT "agent_mcp_bindings_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "ix_agent_mcp_bindings_user_agent_server"
ON "public"."agent_mcp_bindings" USING btree (
  "user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "agent_name" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "mcp_server_name" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

CREATE INDEX IF NOT EXISTS "ix_agent_mcp_bindings_user_server"
ON "public"."agent_mcp_bindings" USING btree (
  "user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST,
  "mcp_server_name" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

DROP TRIGGER IF EXISTS "update_agent_mcp_bindings_updated_at" ON "public"."agent_mcp_bindings";
CREATE TRIGGER "update_agent_mcp_bindings_updated_at" BEFORE UPDATE ON "public"."agent_mcp_bindings"
FOR EACH ROW
EXECUTE PROCEDURE "public"."update_updated_at_column"();
