-- Diji On-site — DijiOne read principal for the Azure SQL onsite schema.
--
-- Run by the On-site SQL Entra admin, connected to the On-site database
-- (DEV: sql-diji-onsite-dev-7d97cf / sqldb-diji-onsite), once per DijiOne
-- environment. Replace the two placeholders first:
--
--   <ENV>           dijione environment name, e.g. dev
--   <PRINCIPAL_ID>  the onsite-api Container App's SYSTEM-ASSIGNED managed
--                   identity principal (object) id:
--                   az containerapp show -g rg-dijione-<ENV> -n onsite-api --query identity.principalId -o tsv
--
-- Grants SELECT only, on exactly the approved objects/columns. No roles, no
-- writes, no DDL, no onsite.Batches, never onsite.Sites.ApiKeyHash. The
-- ingestion API's identity and grants are not touched.
--
-- The user name must begin with the managed identity's display name
-- (the Container App name, onsite-api) when created WITH OBJECT_ID (error 37535).

IF DATABASE_PRINCIPAL_ID('onsite-api-dijione-<ENV>') IS NULL
    CREATE USER [onsite-api-dijione-<ENV>] FROM EXTERNAL PROVIDER WITH OBJECT_ID = '<PRINCIPAL_ID>';

GRANT SELECT ON onsite.AttendanceEvents TO [onsite-api-dijione-<ENV>];
GRANT SELECT ON onsite.Sites (SiteId, DisplayName, TimeZone, IsActive, CreatedUtc) TO [onsite-api-dijione-<ENV>];
GRANT SELECT ON onsite.AgentStatus TO [onsite-api-dijione-<ENV>];

-- Verification (expect exactly the rows above, all SELECT, no role membership):
SELECT dp.name AS principal, p.permission_name, p.state_desc,
       OBJECT_SCHEMA_NAME(p.major_id) + '.' + OBJECT_NAME(p.major_id) AS object_name,
       COL_NAME(p.major_id, p.minor_id) AS column_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON dp.principal_id = p.grantee_principal_id
WHERE dp.name = 'onsite-api-dijione-<ENV>'
ORDER BY object_name, column_name;

SELECT r.name AS role_membership
FROM sys.database_role_members m
JOIN sys.database_principals r ON r.principal_id = m.role_principal_id
JOIN sys.database_principals u ON u.principal_id = m.member_principal_id
WHERE u.name = 'onsite-api-dijione-<ENV>';   -- expect no rows

-- Removal (module-removal runbook):
-- DROP USER [onsite-api-dijione-<ENV>];
