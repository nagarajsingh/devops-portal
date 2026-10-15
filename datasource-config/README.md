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
