# Zolvagraph.org website

Static marketing site for **Zolvagraph** — digital forensics & deleted file recovery.

## Local preview

```bash
cd zolvagraph-web
python3 -m http.server 8080
# open http://localhost:8080
```

## Deploy to zolvagraph.org

### Option A — GitHub Pages (recommended)

1. Create a repo (e.g. `Harrisonegbo/zolvagraph.org` or use `/docs` on the main project).
2. Push the contents of this folder to the `gh-pages` branch or `main` with Pages enabled on `/`.
3. In the repo **Settings → Pages**, set custom domain to `zolvagraph.org`.
4. At your DNS provider, add:

   | Type  | Name | Value |
   |-------|------|--------|
   | A     | @    | `185.199.108.153` |
   | A     | @    | `185.199.109.153` |
   | A     | @    | `185.199.110.153` |
   | A     | @    | `185.199.111.153` |
   | CNAME | www  | `Harrisonegbo.github.io` |

   (Adjust the CNAME target to match your GitHub Pages URL.)

5. The included `CNAME` file sets the domain for GitHub Pages.

### Option B — Cloudflare Pages / Netlify

Connect the repo or drag-and-drop this folder; set custom domain `zolvagraph.org` in the host dashboard.

## Contents

```
index.html      Landing page
css/styles.css  Brand styles (navy / teal)
js/main.js      Nav + year
assets/         Favicon
CNAME           zolvagraph.org
```
