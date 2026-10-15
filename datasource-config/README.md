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


## Runtime entity details

The vault file stores only static environment configuration and credentials. New datasource/entity values are supplied by the dashboard at runtime, including reference entity, target entity, DB host/port, service ID, schema username, datasource type, and ONS nodes when GridLink is selected.

New entity details come from the dashboard and do not need to be pre-created in the vault file. The vault provides a single top-level `password_pattern`, for example `{username}_TXS1T`; the WLST flow substitutes the dashboard-provided schema username at runtime.
