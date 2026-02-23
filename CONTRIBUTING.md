# Contributing

## Prerequisites

- Python 3 available as `python3`
- Node.js 18+
- npm 9+

## Setup

```bash
git clone <repo-url>
cd plati_scraper
```

## Development workflow

1. Create a branch from `main`.
2. Make focused changes.
3. Run checks.
4. Open PR to `main`.

## Checks

```bash
python3 -m py_compile plati_scrape.py mcp_server.py
npm_config_cache=/tmp/npm-cache npm pack --dry-run
python3 -m unittest discover -s tests -p "test_*.py"
```

## Coding rules

- Keep outputs deterministic where possible.
- Keep MCP tool contract stable.
- Do not add machine-specific absolute paths.
- Keep docs updated when behavior changes.

## Release process

### npm package

```bash
npm version patch
npm_config_cache=/tmp/npm-cache npm publish --access public
```

### OpenClaw skill

```bash
npx -y clawhub publish openclaw-plati-mcp-skill --slug plati-mcp-search --name "Plati MCP Search" --version <semver> --changelog "<changes>"
```

## Branch protection recommendation

- Protect `main`:
  - Require PRs before merge
  - Require status checks to pass
  - Restrict direct pushes to owner/admin only

