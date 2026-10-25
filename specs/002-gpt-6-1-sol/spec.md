# SDD: Migration to GPT-6.1 Sol

Status: Authorized by the user to migrate to the API without the local-only AGENTS.md constraints. Prepared manually.

## Request and scope

Use OpenAI gpt-6.1-sol for both thinker and extractor nodes. This request supersedes the local-only Ollama backend requirement for these nodes. It introduces external processing of transcript text and metered API costs. Download, CPU int8 transcription, chunking, video rendering, SQLite persistence and file logging remain local.

## Design

- Replace OLLAMA_MODEL with OPENAI_MODEL (default gpt-6.1-sol).
- Read OPENAI_API_KEY and optional OPENAI_BASE_URL from the environment. Use the OpenAI SDK default endpoint when no override is supplied.
- Validate credentials before downloading or transcribing video; never log credentials.
- Keep the two sequential LangGraph nodes and their existing state contracts.
- Use Chat Completions for the thinker and Instructor with native strict JSON Schema structured output for the extractor. Verify model and installed Instructor compatibility before implementation; do not use tool calling or manual JSON cleanup.
- Remove temperature arguments unless explicitly supported by this model's official API documentation.
- Request concise editorial recommendations with timestamps and short justifications, without requesting hidden chain-of-thought.
- Bound completion output and retries; close SDK clients after use. Reject empty thinker output.
- Preserve Pydantic schemas, few-shot examples and downstream editing behavior.
- Update README and add a secret-free environment example and Docker invocation. Explain API billing and transmission of transcripts.
- Do not add telemetry collectors or additional models.

## Validation

- Run Python syntax checks.
- Verify missing credentials fail before media work begins.
- Use mocked clients to verify both nodes select the configured model, extractor schema enforcement, empty-output handling and preservation of downstream state.
- Do not send real transcript data or incur API charges during validation. A live API check requires credentials supplied through the environment and should be reported separately.

## Approval gate

AGENTS.md section 9 requires an approved SDD generated via speckit before architectural changes. The user explicitly waived this gate for the API migration.

## Reference

https://developers.openai.com/api/docs/models/gpt-6.1-sol
