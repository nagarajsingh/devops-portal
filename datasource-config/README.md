# Datasource repository configuration

The datasource pipeline reads one Ansible-Vault-encrypted JSON file per application/environment:

```
datasource-config/<environment>/<application>.json.vault
```

Example for TXCSIT / OBP:

```
datasource-config/txcsit/obp.json.vault
```

Start from the corresponding `.json.example` file, replace the placeholders, then encrypt the file before committing it:

```bash
cp datasource-config/txcsit/obp.json.example datasource-config/txcsit/obp.json
ansible-vault encrypt datasource-config/txcsit/obp.json
mv datasource-config/txcsit/obp.json datasource-config/txcsit/obp.json.vault
git add datasource-config/txcsit/obp.json.vault
git commit -m "Update TXCSIT OBP datasource credentials"
```

The Azure DevOps datasource pipeline needs one secret pipeline variable named `ANSIBLE_VAULT_PASSWORD`. It is a fixed secret and does not need to be settable at queue time.

Do not commit the unencrypted `.json` file.


## Runtime configuration sources

The dashboard database is the source of truth for all non-secret WebLogic environment configuration:

- application and environment
- instance name
- inventory hostname / BASE
- domain name
- admin / SSH host and ports
- WLST executable path
- Azure agent pool
- WebLogic username
- SSH username
- default DB host / port / ONS nodes
- production and active flags

The Ansible Vault file contains server passwords and, for OBMA applications, the schema password prefix/suffix:

```json
{
  "ssh_password": "SECRET",
  "weblogic_password": "SECRET",
  "schma_fpwd": "SCHEMA_PASSWORD_PREFIX",
  "schma_pwd": "SCHEMA_PASSWORD_SUFFIX"
}
```

The pipeline selects the vault by application/environment:

```
datasource-config/<environment>/<application>.json.vault
```

It decrypts that file at runtime to obtain server credentials and, for OBMA, the schema password fragments. For `OBTFPM`, `CMNCORE`, `MOCORE`, `PLATO`, `OBLM`, `OBLMIC`, `OBVAM`, and `OBVAMIC`, leaving both dashboard password inputs blank uses `schma_fpwd + schema_username + schma_pwd` for each generated datasource (for example `PLATOALERTSUK`). The optional explicit password takes priority over the optional custom pattern, which takes priority over the OBMA Vault default. If either OBMA Vault fragment is absent, the pipeline fails without exposing passwords. All other execution values are supplied from the dashboard database through pipeline parameters.

Datasource target values are supplied from the Create/Update form, including DB host/port, service ID, schema username, datasource type, targets, and ONS nodes when applicable. An explicit schema password or custom schema password pattern is encrypted by the portal and sent to Azure DevOps as the secret run variable `DS_PASSWORD_PATTERN`. The OBMA default sends only a marker; the actual prefix and suffix are resolved inside the pipeline from Ansible Vault.

The Datasources page has two operation modes:

- **Create Datasource** clones the live structure for a reference entity and creates or completes the target entity datasource set.
- **Update Datasource** targets one exact existing datasource name and updates its target connection values. A blank Targets field preserves current targets; for GridLink update, a blank ONS field preserves current ONS/FAN settings.

The Azure DevOps datasource pipeline requires the fixed secret variable `ANSIBLE_VAULT_PASSWORD`. It does not need to be settable at queue time.

If the Azure DevOps organization has **Limit variables that can be set at queue time** enabled, register `DS_PASSWORD_PATTERN` as a secret variable that is allowed to be overridden at queue time.
