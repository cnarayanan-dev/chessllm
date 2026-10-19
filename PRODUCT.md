# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary: the author as researcher.** Runs ChessLLM on their own machine to play small local LLMs, set them against each other, and study how they play and how they fail.
- **Secondary: chess-playing friends and colleagues.** Run it locally to play a model themselves. They know chess well but not the project's research vocabulary.

## Product Purpose

ChessLLM measures how well small local LLMs play chess. Models play humans (**Play LLM**), each other (**LLM faceoff**) and opponents of fixed strength (**Anchor match**). Every game, move and LLM attempt is logged so the results can be analysed.

Success means three things:

- **Shareable findings.** Results are credible and clear enough to go into a write-up, post or paper.
- **Failure insight.** The product makes visible *how* a model fails: illegal moves by kind, notation slips, retries, legal-move streaks, forfeits and chaos moves.
- **Fun to play.** A game against a model, including its mistakes and its chaos-rules behaviour, is enjoyable in its own right.

## Positioning

Most LLM chess benchmarks report a single score for a model. ChessLLM treats the **Player configuration** as the thing being rated: model, thinking, LLM constraints (Free / Listed / Blind enforced / Listed enforced), Standard or Chaos rules, retry feedback, sampling and prompt. It keeps each failure as data rather than hiding it. It also shows two separate Elos, the **Rating** (from results) and the **Move-quality estimate** (from moves), and treats the gap between them as a finding.

## Operating Context

- Runs on localhost: a Python (FastAPI) backend serves `chessllm/static/` and talks to Ollama models running locally (currently qwen3.5:9b, llama3:8b, gemma3:12b).
- Games are written to `games/` as JSON Lines logs, plus a PGN file when a game ends.
- Domain language is defined in `CONTEXT.md`, and decisions are recorded in `docs/adr/`. UI copy should use those terms and avoid the "_Avoid_" synonyms.
- An LLM turn can take seconds or longer (thinking, retries), so waiting on the model is a normal state of the UI.

## Capabilities and Constraints

- **Local-only.** Models come from Ollama on the user's machine. No accounts, no cloud and no hosted service.
- **Desktop-first.** Designed mainly for a laptop or desktop screen. Mobile is secondary.
- The backend owns move legality (ADR 0001). It is lenient on legality and strict on notation (ADR 0002). Metrics such as legal-move streak do not apply under Enforced decoding (ADR 0003).
- Not built yet or still in progress: LLM faceoff and Anchor match UI, rating and analytics views (prototypes in `chessllm/static/prototype-*.html`, `prototypes/`), and an Elo estimation method (`docs/research/elo-estimation.md`).

## Brand Commitments

- Name: **ChessLLM**.
- Merida pieces by Armando Hernandez Marroquin, GPLv2+. The credit must be kept.
- The current board takes its look from lichess (brown board, square tints, legal-move dots, move sound). This is the incumbent look, not a binding commitment.

## Evidence on Hand

- Real game logs in `games/`.
- Research notes: `docs/research/elo-estimation.md`, `docs/research/llm-chess-notation.md`.
- There are no published ratings, benchmark results, users or testimonials yet. Do not invent any of them.

## Product Principles

1. **Failures are data.** Show illegal moves, slips, retries and forfeits clearly. Do not smooth them over.
2. **Name the configuration.** A result always says which Player configuration produced it, and Ratings always come with their uncertainty.
3. **Credible enough to share.** Anything that may end up in a write-up must be precise, honest about sample size, and easy to export or screenshot.
4. **Waiting is part of play.** The model's thinking time should feel deliberate and show what is happening, not look like the app has frozen.
5. **Chess players first, jargon second.** A visiting player must be able to start and finish a game without learning the research vocabulary.
