# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog and Semantic Versioning.

## [Unreleased]

### Added
- Service layer for business operations (`codeindex.service`).
- Project-level defaults via `.codeindex.toml` discovery.
- Migration framework with `codeindex_schema_migrations`.
- Extended doctor checks (DB latency/version/privileges/migrations/package import).
- Safer delete flow with dry-run and typed confirmation.
- Metadata backup commands (`export` / `import`).
- Additional test coverage for edge cases and lifecycle paths.

### Changed
- Migration bootstrap centralized in service layer.
- Catalog access layer now focused on CRUD operations.
