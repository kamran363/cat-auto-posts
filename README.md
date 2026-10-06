# Cat Auto Posts 🐱

Fully automatic daily posting for the **Little Muse** cat page.

- 🎬 3 reels daily
- 🖼️ 3 images daily
- 📝 3 posts daily

## Setup

1. Add the long-lived Page token as `FB_PAGE_TOKEN` in Settings > Secrets and variables > Actions.
2. The workflow `.github/workflows/daily-posts.yml` (created via web UI) posts the next ready item from `content/manifest.json` at each scheduled slot.
3. Daily content is generated and pushed by the content cron.

## Queue

`content/manifest.json` holds the queue; `content/state.json` tracks the index.
