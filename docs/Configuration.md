# Configuration

`tgcf` is primarily configured via a single JSON file (`tgcf.config.json`) along with environment variables for sensitive or runtime-specific parameters.

## Environment Variables

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `PASSWORD` | Password used to authenticate and protect the web interface | `tgcf` |
| `TGCF_MODE`| The execution mode (`live` or `past`) when using the CLI | None (Failed run if missing via CLI) |

You can manage these via a `.env` file placed in the same directory where you run `tgcf`:

```shell
PASSWORD=your_secure_password
TGCF_MODE=live
```

## Config JSON (`tgcf.config.json`)

The config file dictates routing and plugin behavior. It is generated and modified automatically if you use the Web UI. For manual deployment, it looks roughly like this:

```json
{
  "forwards": [
    {
      "source": "source_chat_id",
      "dest": ["dest_chat_id_1", "dest_chat_id_2"]
    }
  ],
  "admins": ["your_admin_id"],
  "plugins": {
    "filter": {},
    "format": {},
    "replace": {}
  }
}
```

*Note: It is highly encouraged to use the Web UI (`tgcf-web`) to build your initial configuration file securely and without syntax errors.*
