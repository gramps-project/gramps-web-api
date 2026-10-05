# Contributing to Gramps Web API

Thank you for your interest in contributing! Gramps Web API is maintained by very few people in their spare time, so a little structure goes a long way. Everything below exists to make your contribution easier to act on.

## Where does it go?

| Your situation                                              | Where                                                                     |
| ----------------------------------------------------------- | ------------------------------------------------------------------------- |
| Trouble installing, deploying or configuring Gramps Web API | [Gramps forum](https://gramps.discourse.group/c/gramps-web/28)            |
| A question, or you're not sure it's a bug                   | [Gramps forum](https://gramps.discourse.group/c/gramps-web/28)            |
| Something server-side (API, search, import/export)          | [issue here](https://github.com/gramps-project/gramps-web-api/issues)     |
| A bug or idea in a frontend, e.g. Gramps Web                | that frontend's repository, e.g. [gramps-web](https://github.com/gramps-project/gramps-web/issues) |
| The Gramps Web Sync addon for Gramps desktop                | [gramps-web-sync](https://github.com/DavidMStraub/gramps-web-sync/issues) |

For setup problems the forum will usually get you an answer faster, since many more configurations are running out there than we could ever test.

## Issues

Describe the problem: what happened, what you expected, and how to reproduce it. That is the part only you can provide.

If you have an idea about the cause or the fix, put it in the optional section at the end and keep it brief. Leaving it empty is completely fine. A clearly described problem is already the most useful thing you can send us.

Please keep issues as short as they can be while still complete. A short issue is quicker to act on.

## Pull requests

**For features and larger changes, please open an issue first and wait for a reply.**

Small, self-contained fixes, such as a bug fix with a test, a documentation fix or a typo, are welcome as a pull request directly. No separate issue needed.

There is a good reason for this. Reviewing a pull request costs a maintainer many times what reading an issue costs. An issue lets us reply with "yes, go ahead", "let's solve it differently", or "someone is already on it" while your evening is still free. An issue and a pull request opened five minutes apart leave no room for that conversation.

So please send issues freely. Contributions are genuinely welcome, and this is mostly about the order they arrive in.

In the pull request itself, link the issue if there is one, and describe the change and how you tested it. The problem description belongs in the issue, so there is no need to repeat it here.

## Using AI assistants

Using an AI assistant to help write code, issues or pull requests is fine. Two things we ask:

**Read it before you post it.** You are the author, and you'll be the one answering follow-up questions about it.

**Post as yourself.** An assistant should never write as though it were a human contributor.

And please keep the human parts human. A greeting, a thank you, a sentence about what you were actually trying to do when you hit the bug: that is very often the part that tells us what the real problem was.

If you point an agent at this repository, [AGENTS.md](AGENTS.md) holds the project conventions and a short version of the rules above.

## Development

Setup, coding standards and API details are in the [developer documentation](https://www.grampsweb.org/development/dev/). Please include tests and documentation updates where applicable.

### Testing remote embeddings (optional)

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
   GRAMPSWEB_VECTOR_EMBEDDING_BASE_URL: http://ollama:11434
   GRAMPSWEB_VECTOR_EMBEDDING_MODEL: nomic-embed-text
   ```

4. Restart the devcontainer to pick up the new environment variables.

## Code of conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).
