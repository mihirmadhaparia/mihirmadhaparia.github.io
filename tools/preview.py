#!/usr/bin/env python3
"""Local preview builder for mihirmadhaparia.github.io.

Renders the Jekyll pages into a static `_site/` folder using plain Python so the
site can be previewed in a browser via file:// without installing Jekyll/Ruby.
Supports the subset of Liquid this site uses:
  - {{ '/path' | relative_url }}
  - {{ content }}, {{ site.title }}, {{ site.description }}
  - {{ page.title }}, {{ page.excerpt | ... }}
  - {{ page.ticker | default: "..." }}
  - {% if page.url == '/x/' %}..{% else %}..{% endif %}
  - {% if page.title %} / {% if page.excerpt %} / {% if page.needs_model %}
  - {% comment %}..{% endcomment %}

Usage:  python3 tools/preview.py      Output: ./_site/ (open _site/index.html)
"""
import os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")
LAYOUT = os.path.join(ROOT, "_layouts", "default.html")

def load_config():
    cfg = {"title": "", "description": "", "baseurl": "/"}
    with open(os.path.join(ROOT, "_config.yml"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^(title|description|baseurl|url):\s*"?(.*?)"?\s*(#.*)?$', line)
            if m:
                cfg[m.group(1)] = m.group(2)
    return cfg

def split_front_matter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        fm_raw = text[3:end].strip()
        body = text[end + 4:].lstrip("\n")
        fm = {}
        for line in fm_raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip('"')
        return fm, body
    return {}, text

def rel_prefix(page_url):
    s = page_url.strip("/")
    depth = (s.count("/") + 1) if s else 0
    return "../" * depth if depth else "./"

def resolve_liquid(text, ctx):
    prefix = ctx["prefix"]
    # strip {% comment %}..{% endcomment %}
    text = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", text, flags=re.S)
    # {{ '/x' | relative_url }}
    def relurl(m):
        resolved = prefix + m.group(1).lstrip("/")
        if resolved.endswith("/"):
            resolved += "index.html"
        return resolved
    text = re.sub(r"\{\{\s*'([^']*)'\s*\|\s*relative_url\s*\}\}", relurl, text)
    # {{ page.ticker | default: "..." }}
    def ticker(m):
        return ctx.get("page_ticker") or m.group(1)
    text = re.sub(r'\{\{\s*page\.ticker\s*\|\s*default:\s*"(.*?)"\s*\}\}', ticker, text, flags=re.S)
    # {% if page.url == '/x/' %}A{% else %}B{% endif %}
    def ifeq(m):
        target, a, b = m.group(1), m.group(2), m.group(3) or ""
        return a if ctx["page_url"] == target else b
    text = re.sub(r"\{%\s*if page\.url == '([^']*)'\s*%\}(.*?)(?:\{%\s*else\s*%\}(.*?))?\{%\s*endif\s*%\}", ifeq, text, flags=re.S)
    # boolean front-matter conditionals
    for key in ("title", "excerpt", "needs_model", "ticker"):
        truthy = bool(ctx.get("page_" + key))
        text = re.sub(r"\{%\s*if page\." + key + r"\s*%\}(.*?)\{%\s*endif\s*%\}",
                      (lambda a=truthy: (lambda m: m.group(1) if a else ""))(), text, flags=re.S)
    # scalars
    text = text.replace("{{ content }}", ctx.get("content", ""))
    text = text.replace("{{ site.title }}", ctx["site"]["title"])
    text = text.replace("{{ site.description }}", ctx["site"]["description"])
    text = text.replace("{{ page.title }}", ctx.get("page_title", ""))
    return text

def out_path_for(permalink):
    p = permalink.strip("/")
    return os.path.join(OUT, "index.html") if not p else os.path.join(OUT, p, "index.html")

def sync_assets(src, dst):
    """Copy assets, skipping files already present with the same size (fast rebuilds)."""
    if not os.path.isdir(src):
        return
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        outdir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(outdir, exist_ok=True)
        for fn in files:
            sp, dp = os.path.join(root, fn), os.path.join(outdir, fn)
            try:
                if os.path.exists(dp) and os.path.getsize(dp) == os.path.getsize(sp):
                    continue
            except OSError:
                pass
            shutil.copyfile(sp, dp)

def main():
    cfg = load_config()
    with open(LAYOUT, encoding="utf-8") as f:
        layout = f.read()
    pages = sorted(fn for fn in os.listdir(ROOT) if fn.endswith(".html"))
    os.makedirs(OUT, exist_ok=True)
    built = []
    for fn in pages:
        with open(os.path.join(ROOT, fn), encoding="utf-8") as f:
            fm, body = split_front_matter(f.read())
        if "permalink" not in fm:
            continue  # skip non-page html (safety)
        permalink = fm["permalink"]
        prefix = rel_prefix(permalink)
        ctx = {"site": cfg, "prefix": prefix, "page_url": permalink,
               "page_title": fm.get("title", ""), "page_excerpt": fm.get("excerpt", ""),
               "page_needs_model": fm.get("needs_model", ""), "page_ticker": fm.get("ticker", "")}
        ctx["content"] = resolve_liquid(body, ctx)
        html = resolve_liquid(layout, ctx)
        dest = out_path_for(permalink)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(html)
        built.append(os.path.relpath(dest, ROOT))
    sync_assets(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    print("Built %d pages into %s" % (len(built), OUT))
    for b in sorted(built):
        print("  ", b)
    print("\nOpen this in a browser:\n  ", os.path.join(OUT, "index.html"))
    print("\nNOTE: 3D models (.glb) will NOT load over file:// (browser blocks it).")
    print("      To preview models, run:  python3 tools/preview.py --serve")

def serve(port=8000):
    import http.server, socketserver
    os.chdir(OUT)
    handler = http.server.SimpleHTTPRequestHandler
    for p in range(port, port + 20):
        try:
            httpd = socketserver.TCPServer(("", p), handler)
        except OSError:
            continue
        url = "http://localhost:%d/" % p
        print("\nServing preview (models will load) at:\n  ", url)
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")
        return
    print("Could not bind a port in range %d-%d." % (port, port + 19))

if __name__ == "__main__":
    main()
    if "--serve" in sys.argv:
        serve()
