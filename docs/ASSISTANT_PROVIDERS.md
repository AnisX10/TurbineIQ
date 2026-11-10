# Assistant providers

Provider preset documentation was checked on **2026-11-10**. These are documented API defaults, not guarantees of access, price, free quota, throughput, or data retention. Provider catalogs and terms change; confirm the linked documentation before deploying or sharing information.

## Presets

| Provider selector | Default base URL | Default model | Adapter | Verification and caveats |
|---|---|---|---|---|
| `groq` | `https://api.groq.com/openai/v1` | `openai/gpt-oss-120b` | Chat Completions | Groq documents the compatible base URL and both GPT-OSS 120B and 20B. Its current GPT-OSS tool-use page reports no parallel tool use for those models, so TurbineIQ requests sequential generation for Groq while still accepting and safely executing multiple returned calls. [OpenAI compatibility](https://console.groq.com/docs/openai), [GPT-OSS model](https://console.groq.com/docs/model/openai/gpt-oss-120b), [tool-use model support](https://console.groq.com/docs/tool-use/overview). |
| `cerebras` | `https://api.cerebras.ai/v1` | `gpt-oss-120b` | Chat Completions | The current shared model catalog lists `gpt-oss-120b`; the chat endpoint documents tool calls and parallel tool calls. A Cerebras-hosted GPT-OSS 20B model was not found in the current shared catalog, so no 20B Cerebras preset is claimed. [Model catalog](https://inference-docs.cerebras.ai/models/overview), [Chat Completions](https://inference-docs.cerebras.ai/api-reference/chat-completions), [tool calling](https://inference-docs.cerebras.ai/capabilities/tool-use), [OpenAI compatibility](https://inference-docs.cerebras.ai/resources/openai). |
| `openrouter` | `https://openrouter.ai/api/v1` | `openai/gpt-oss-120b` | Chat Completions | Current model pages list both `openai/gpt-oss-120b` and `openai/gpt-oss-20b` and document tool calling. Upstream tool support varies by routed provider, and hosted access is not guaranteed to be free. [Quickstart/base URL](https://openrouter.ai/docs/quickstart), [GPT-OSS 120B](https://openrouter.ai/openai/gpt-oss-120b), [GPT-OSS 20B](https://openrouter.ai/openai/gpt-oss-20b). |
| `ollama` | `http://localhost:11434/v1` | `gpt-oss:20b` | Chat Completions | Ollama's current compatibility guide uses this base URL and model ID. The local server ignores its required SDK placeholder key; TurbineIQ supplies one internally when no key is configured. Hardware, memory, and local model availability are the operator's responsibility. [Ollama OpenAI compatibility](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx). |
| `openai` | `https://api.openai.com/v1` | `gpt-5.5` | Responses API | The existing Responses integration remains available, and current OpenAI model docs list GPT-5.5 function calling through Responses. GPT-OSS 120B/20B weights are not served through the OpenAI API; use a hosting provider or self-host them. [GPT-5.5 model](https://developers.openai.com/api/docs/models/gpt-5.5), [OpenAI GPT-OSS availability](https://help.openai.com/en/articles/11870455-openai-open-weight-models-gpt-oss). |
| `custom` | Required | Required | Chat Completions | Use for an OpenAI-compatible endpoint not in the preset list, including the Hugging Face Router. The Hugging Face guide documents `https://router.huggingface.co/v1`, `HF_TOKEN`, and `openai/gpt-oss-120b` as a tool-capable chat model. [Hugging Face chat completions](https://huggingface.co/docs/inference-providers/tasks/chat-completion). |

The OpenAI-compatible adapter submits only chat messages, tool schemas, selected model, and the configured output limit. It reads response text and function calls only; reasoning fields are ignored. The OpenAI Responses adapter sets `store=false` and does not retain hidden reasoning fields.

## Environment precedence

`TURBINEIQ_LLM_API_KEY` takes precedence over provider-specific variables. Supported fallbacks are `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_API_KEY`, `OPENAI_API_KEY`, and `TURBINEIQ_CUSTOM_API_KEY`. A custom provider may also use `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN`. Ollama may run without a user key. `TURBINEIQ_LLM_BASE_URL` and `TURBINEIQ_LLM_MODEL` override the selected preset.

Legacy `OPENAI_API_KEY`, `TURBINEIQ_OPENAI_MODEL`, and `TURBINEIQ_OPENAI_BASE_URL` remain supported when `TURBINEIQ_LLM_PROVIDER` is unset. Timeout, max output tokens, and max tool rounds use `TURBINEIQ_LLM_TIMEOUT_SECONDS`, `TURBINEIQ_LLM_MAX_TOKENS`, and `TURBINEIQ_LLM_MAX_TOOL_ROUNDS`; tool rounds are always capped at three.

## Data handling

Local deterministic tools remain the default. Cloud mode sends the question, assistant instructions, available tool schemas, selected synthetic context, and any tool outputs to the selected provider. Retrieved excerpts are excluded until the separate document-sharing option is enabled; excerpt text is marked as untrusted data in the tool transcript. Check provider logging, retention, training, and geographic-processing policies before use. API keys stay in the local API process and are never returned from `/api/assistant/status` or `/api/assistant/test`.

No provider quota numbers are embedded in the application or documentation. Hosted access, account requirements, usage tiers, pricing, and limits must be checked with each provider at the time of use.
