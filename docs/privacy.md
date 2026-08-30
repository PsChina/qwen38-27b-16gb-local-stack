# Public repository privacy checklist

Before committing local changes, verify that the tree contains none of the following:

- real IP addresses or private DNS names;
- SSH usernames, passwords, tokens, or key material;
- absolute paths containing a personal username;
- raw proxy/server logs;
- conversation transcripts or tool results;
- model files or generated caches.

Use the ignored local files for machine-specific values. The checked-in files must remain portable templates.

## API keys and the DSH example

The DeepSeek Harness example (`configs/dsh/qwen38.provider.example.*`) references the API key by the environment-variable name `QWEN38_API_KEY`; the value belongs in DSH's user-local credential store, not in the repository. Never replace a checked-in example with a real key. The local no-auth compatibility endpoint accepts the dummy value `local`:

```yaml
# ~/.dsh/.credentials.yaml
version: 1
refs:
  QWEN38_API_KEY: local
```

The DSH example uses the anonymized `http://qwen-host.example:8098/v1` placeholder as its local-network base URL. Replace it only in a private copy if your proxy listens elsewhere, and never commit production endpoints or remote credentials. The credentials file should remain mode `0600`.
