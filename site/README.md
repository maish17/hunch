# Project Respite website

The public showcase site, published with GitHub Pages at **https://maish17.github.io/hunch/** (the repo-root `index.html` redirects to this folder).

| File | What it is |
|---|---|
| `index.html` | The page. All text lives here. |
| `style.css` | All styling. Palette: blue `#354c70`, white `#f7f0f5`, yellow `#ffeb77` (accent only). One typeface: Archivo. |
| `demo/` | The embedded dashboard demo. It loads the real `dashboard/*.js` and `fixtures/` from the repo, so dashboard changes show up here automatically. Only `demo/index.html` (header) and `demo/demo.css` (brand colours) are website-specific. |
| `assets/` | Logo (`logo-256.png`), favicon, team photos. |

## Preview locally

From the repo root run `make dashboard`, then open http://localhost:8000/site/

## Common edits

- **Team photos:** put a square photo in `assets/team/` (e.g. `max.jpg`), then in `index.html` change that person's `src="assets/team/placeholder.svg"` to `src="assets/team/max.jpg"`. Each spot has a comment saying exactly this.
- **Progress section:** edit the three lists under `id="progress"` as work gets done.
- **Example chart:** the "wearing wheel bearing" chart is a static drawing made from `fixtures/active_work_order/robot_P2-02.json`. It's simulated example data and is labelled that way on the page. Keep that label.

## Publishing

Every push to `main` updates the live site within a minute or two. One-time setup (already needed only once):

1. Repo **Settings → General → Danger Zone → Change visibility → Public**.
2. Repo **Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main`, folder `/ (root)` → Save**.
3. Wait ~1 minute, then open https://maish17.github.io/hunch/

The empty `.nojekyll` file in the repo root tells GitHub Pages to serve files as-is. Don't delete it.
