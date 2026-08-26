# Vaidehi Telegram Bot

A Hinglish-speaking persona chatbot for Telegram, built with `python-telegram-bot`,
Grok (xAI) for generation, and Postgres + pgvector for memory/embeddings.

## What this includes

- **Persona chat** (`handlers/chat.py`) — warm, playful, teasing Hinglish personality.
  Kept PG: flirty/affectionate banter is fine, but the prompt does **not** instruct the
  model to engage in explicit/adult content, and it does not instruct the bot to lie
  about being an AI if asked directly. It's built to stay in character and deflect
  meta-questions gracefully instead of scripted denial — see `persona.py` comments.
- **Key rotation** (`grok_client.py`) — round-robins across up to 5 Grok API keys,
  with automatic fallback to the next key on rate-limit/error responses.
- **Postgres + pgvector** (`db.py`, `schema.sql`) — stores messages, per-user profiles,
  and embeddings for semantic memory retrieval (using a HuggingFace sentence-transformer
  model run locally via `sentence-transformers`).
- **Group features** (`handlers/group_commands.py`) — implements the commands from your
  screenshots: `/loveboard`, `/mylove`, `/couple`, `/breakup`, `/compliment`, `/roast`.
  When the bot is added to a group, it registers all members it sees interacting so the
  couple-matching logic has a pool to draw from.

## Setup

1. **Postgres**: create a database, enable the `vector` extension, then run `schema.sql`.

   ```bash
   createdb vaidehi
   psql vaidehi -c "CREATE EXTENSION IF NOT EXISTS vector;"
   psql vaidehi -f schema.sql
   ```

2. **Python env**:

   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Config**: copy `.env.example` to `.env` and fill in:
   - `TELEGRAM_BOT_TOKEN`
   - `GROK_API_KEY_1` through `GROK_API_KEY_5` (as many as you have, minimum 1)
   - `DATABASE_URL`
   - `EMBEDDING_MODEL` (defaults to a small multilingual sentence-transformers model,
     good for Hinglish text)

4. **Run**:

   ```bash
   python main.py
   ```

## Notes on the guardrails

- The system prompt template lives in `persona.py`. It explicitly instructs the model
  never to reveal, quote, or paraphrase its own instructions, and never to discuss the
  fact that it has a "system prompt" at all — it deflects in-character
  ("hehe, that's classified 🙈") rather than confirming or denying anything about its
  underlying architecture.
- It does **not** instruct the model to explicitly claim humanity if directly and
  sincerely asked "are you an AI/bot?" — that crosses into deception rather than
  in-character deflection, so I left it out. If you want a specific deflection line for
  that exact question, it's an easy one-line addition to `persona.py`.
- Sexual content is capped at flirty/suggestive, non-graphic. If you want a stricter or
  looser line, that's a single paragraph to edit in `persona.py`.
- Since the bot is open to any Telegram user (including inside groups with no age
  gating), there's no reliable way to verify ages — so explicit/adult content generation
  is intentionally left out of this build. Keep that in mind before extending it.

## Extending

- `handlers/group_commands.py` has clear extension points for new commands.
- `db.py` exposes `save_message()`, `get_recent_context()`, and
  `semantic_search()` if you want to add long-term memory recall to responses.
- `grok_client.py`'s `GrokClient.generate()` is the single choke point for all model
  calls — add logging/moderation hooks there.
