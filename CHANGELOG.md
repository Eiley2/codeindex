# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Service layer centralizing all business operations (`codeindex.service`).
- Project-level configuration via `.codeindex.toml` auto-discovery (walks from cwd toward root).
- Schema migration framework backed by `codeindex_schema_migrations` table.
- Extended `doctor` checks: DB latency, server version, privilege verification, applied migrations, and package import validation.
- Safer `delete` flow: dry-run preview and typed index-name confirmation before applying.
- Metadata backup commands: `export` (catalog to JSON) and `import` (JSON to catalog, with dry-run).
- Additional test coverage for edge cases and full index lifecycle paths.
- Self-update commands: `codeindex check-update` and `codeindex update`.
- Automatic (cached) update notification when a newer release is available.
- Agent template management commands: `codeindex skills set` and `codeindex skills update`.
- Embedding model presets and setup commands: `codeindex embedding-models` and `codeindex setup`.
- CLI support for per-run embedding overrides via `--embedding-model` on `index` and `reindex`.
- Project-level embedding model option: `[index].embedding_model` in `.codeindex.toml`.
- Expanded test coverage for embedding model precedence and setup behavior.
- OpenRouter embedding support (`embedding_provider = "openrouter"`) for index, reindex, and search flows.
- New CLI override flag `--embedding-provider` on `index` and `reindex`.
- zsh autocomplete support with `codeindex completion zsh` and `codeindex completion zsh --install`.
- Interactive setup flow (`codeindex setup`) with menu-based selection for presets/provider/model and prompts for overwrite/database URL.

### Changed
- Migration bootstrap centralized in the service layer; no longer performed ad-hoc in CLI commands.
- Catalog access layer (`codeindex.catalog`) now focused exclusively on CRUD operations.
- Setup/config now persists both `embedding_provider` and `embedding_model`.
- Catalog metadata now stores embedding provider to keep query/index provider-model alignment.
- Package version bumped to `1.0.7` to prevent stale install cache behavior.
- Removed `codeindex status`; `codeindex list` is now the single command for index discovery.
- `codeindex list` now includes chunk count and last indexed timestamp for managed indexes.
- Search now uses the indexed catalog model when available, improving query/index model alignment.
