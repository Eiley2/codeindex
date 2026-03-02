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

### Changed
- Migration bootstrap centralized in the service layer; no longer performed ad-hoc in CLI commands.
- Catalog access layer (`codeindex.catalog`) now focused exclusively on CRUD operations.
