"""PostgreSQL triggers that make audit_event append-only (SEC-09).

They apply to every role, including the table owner, so a bug or a stolen app credential
cannot rewrite history. Production also runs the app as a role without UPDATE/DELETE/TRUNCATE
on this table and migrates as a different role, so the app role cannot drop the triggers.
"""

TABLE = "audit_auditevent"


def forward_sql() -> str:
    return f"""
CREATE FUNCTION audit_reject_change() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit events are append-only (%% on %%)', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_no_update_delete BEFORE UPDATE OR DELETE ON {TABLE}
  FOR EACH ROW EXECUTE FUNCTION audit_reject_change();
CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON {TABLE}
  FOR EACH STATEMENT EXECUTE FUNCTION audit_reject_change();
"""


def reverse_sql() -> str:
    return f"""
DROP TRIGGER audit_no_truncate ON {TABLE};
DROP TRIGGER audit_no_update_delete ON {TABLE};
DROP FUNCTION audit_reject_change();
"""
