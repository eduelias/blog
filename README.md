# blog.du7.dev

Source for the Du7 Engineering blog, served via **GitHub Pages + Jekyll** at
[blog.du7.dev](https://blog.du7.dev).

## Structure

- `_posts/` — blog posts (Markdown with front-matter, newest shown first).
- `_layouts/` — `default.html` (dark theme) and `post.html`.
- `index.html` — post listing (latest on top), each links to its own page.
- `assets/` — images/charts.
- `_config.yml` — Jekyll config.
- `CNAME` — custom domain (`blog.du7.dev`).

## Add a post

Create `_posts/YYYY-MM-DD-slug.md` with front-matter:

```yaml
---
layout: post
title: "Your title"
date: YYYY-MM-DD 12:00:00 +0200
author: Eduardo Elias
tags: [tag1, tag2]
---
```

Push to `main`; GitHub Pages builds and deploys automatically.

## Local preview (optional, needs Ruby 3.x)

```bash
bundle install
bundle exec jekyll serve
```

Charts are generated from experiment logs via `make_charts.py`.
