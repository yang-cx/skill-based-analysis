# CLI Usage Examples

## Inspect

```bash
rootmltool inspect --path ./data/sample.root
```

JSON output:

```bash
rootmltool inspect --path ./data/sample.root --json
```

## Extract

Extract branches into JSON-serializable dict output:

```bash
rootmltool extract \
  --path ./data/sample.root \
  --tree Events \
  --branches pt eta charge \
  --output-format dict \
  --json
```

Apply filters:

```bash
rootmltool extract \
  --path ./data/sample.root \
  --tree Events \
  --branches pt eta \
  --filter pt:gt:20 \
  --filter charge:eq:1
```

Export parquet:

```bash
rootmltool extract \
  --path ./data/sample.root \
  --tree Events \
  --branches pt eta \
  --output-format parquet \
  --output-path ./artifacts/events_filtered.parquet
```
