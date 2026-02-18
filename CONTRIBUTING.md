# Contributing to Gramps Web API

Welcome, and thank you for your interest in contributing to Gramps Web API! Your efforts help make this project better for everyone.

## How to Contribute

### Reporting Issues
- Found a bug or have a feature request? [Open an issue](https://github.com/gramps-project/gramps-web-api/issues) to let us know!
- Provide as much detail as possible, including steps to reproduce the issue or a clear description of the feature idea.

### Proposing Features
- **Before implementing a new feature**, please open an issue to discuss your proposal. This helps avoid duplicate work and ensures alignment with project goals.

### Development Guidelines
- Follow the [developer documentation](https://www.grampsweb.org/development/dev/) for setup, coding standards, and API details.
- Ensure your changes include appropriate tests and documentation updates where applicable.

#### Testing Remote Embeddings (Optional)

The devcontainer includes an optional [Ollama](https://ollama.com/) service for testing the remote embedding API without external dependencies.

1. Start the Ollama service:
   ```bash
   docker compose -f .devcontainer/docker-compose.yml --profile ollama up -d ollama
   ```

2. Pull an embedding model:
   ```bash
   docker compose -f .devcontainer/docker-compose.yml exec ollama ollama pull nomic-embed-text
   ```

3. In `.devcontainer/docker-compose.yml`, comment out the local `GRAMPSWEB_VECTOR_EMBEDDING_MODEL` line and uncomment the Ollama lines:
   ```yaml
   # GRAMPSWEB_VECTOR_EMBEDDING_MODEL: sentence-transformers/distiluse-base-multilingual-cased-v2
   GRAMPSWEB_EMBEDDING_BASE_URL: http://ollama:11434
   GRAMPSWEB_VECTOR_EMBEDDING_MODEL: nomic-embed-text
   ```

4. Restart the devcontainer to pick up the new environment variables.

### Code of Conduct
- Please read and adhere to our [Code of Conduct](CODE_OF_CONDUCT.md) to ensure a welcoming and inclusive environment for all contributors.


### Communication
- For general discussions or questions, join our [Discourse forum](https://gramps.discourse.group/).
- Engage respectfully and collaboratively with the community.

We look forward to your contributions!
