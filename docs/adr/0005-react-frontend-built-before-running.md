# The frontend is a React app with shadcn/ui, built before running

The page was one static `index.html` with a plain JavaScript module script, served as it is by FastAPI. It became the busiest file in the repo, and the next screens (Anchor match, the analytics views with their tables, tabs and rating charts, and settings whose fields depend on each other) would all have to be hand-built in plain JavaScript. The frontend becomes a React + TypeScript app in `frontend/`, built with Vite, styled with Tailwind and shadcn/ui, and generated into `chessllm/static/dist/`, which is git-ignored. Running the app now needs Node and `pnpm build` before `uv run python -m chessllm`. FastAPI serves the build and gives a clear error when it is missing.

## Considered Options

- **Basecoat UI on the existing page** (shadcn's look as plain HTML and Tailwind classes): no build step and no rewrite, but no React components, no data tables or charts, and every rule between settings fields stays hand-wired in plain JavaScript.
- **Commit the built files**, so a friend who plays needs only `uv`: rejected for noisy diffs and a built copy that can fall out of date with its source. Building on startup was rejected too: it still needs Node, and it makes startup slower and more complicated.
- **Run both frontends side by side**, building new screens in React and porting the play page later: rejected because the app would have two looks, and two pages would drive the one current game. The play page was ported in one go, and no new features went into `index.html` during the port.

## Consequences

- The TypeScript types for the API are generated from FastAPI's API description, and a test fails when they are out of date. A Pydantic change that breaks the page therefore fails the build, not the browser. Every endpoint declares a response model.
- The board stays cm-chessboard, installed from npm and wrapped in one React component, so the Merida pieces, markers, promotion dialog and move sound are unchanged.
- The page is no longer tested by looking for strings in the HTML. Vitest covers the game reducer and the components that carry rules. Playwright runs the built app against FastAPI with scripted LLM players.
- The port used shadcn's default theme. The app's own look is set afterwards by changing shadcn's CSS variables and recorded in `DESIGN.md`.
