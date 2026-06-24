#!/usr/bin/env python3
"""Local preview builder for mihirmadhaparia.github.io.

Renders the Jekyll pages into a static `_site/` folder using plain Python so the
site can be previewed in a browser via file:// without installing Jekyll/Ruby.
Supports only the subset of Liquid this site uses (relative_url, content,
site/page vars, and simple page.url == '...' conditionals).

Usage:  python3 tools/preview.py
Output: ./_site/  (open _site/index.html in a browser)
"""
import os, re, shutil

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
    def relurl(m):
        resolved = prefix + m.group(1).lstrip("/")
        if resolved.endswith("/"):
            resolved += "index.html"
        return resolved
    text = re.sub(r"\{\{\s*'([^']*)'\s*\|\s*relative_url\s*\}\}", relurl, text)
    def ifeq(m):
        target, a, b = m.group(1), m.group(2), m.group(3) or ""
        return a if ctx["page_url"] == target else b
    text = re.sub(r"\{%\s*if page\.url == '([^']*)'\s*%\}(.*?)(?:\{%\s*else\s*%\}(.*?))?\{%\s*endif\s*%\}", ifeq, text, flags=re.S)
    has_title = bool(ctx.get("page_title"))
    text = re.sub(r"\{%\s*if page\.title\s*%\}(.*?)\{%\s*endif\s*%\}", (lambda m: m.group(1) if has_title else ""), text, flags=re.S)
    text = re.sub(r"\{%\s*if page\.excerpt\s*%\}(.*?)\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}", (lambda m: m.group(2)), text, flags=re.S)
    text = text.replace("{{ content }}", ctx.get("content", ""))
    text = text.replace("{{ site.title }}", ctx["site"]["title"])
    text = text.replace("{{ site.description }}", ctx["site"]["description"])
    text = text.replace("{{ site.baseurl }}", prefix.rstrip("/") or ".")
    text = text.replace("{{ page.title }}", ctx.get("page_title", ""))
    return text

def out_path_for(permalink):
    p = permalink.strip("/")
    return os.path.join(OUT, "index.html") if not p else os.path.join(OUT, p, "index.html")

def main():
    cfg = load_config()
    with open(LAYOUT, encoding="utf-8") as f:
        layout = f.read()
    pages = [fn for fn in os.listdir(ROOT) if fn.endswith(".html") and fn != "README.html"]
    pages.append("README.html")
    os.makedirs(OUT, exist_ok=True)
    built = []
    for fn in pages:
        with open(os.path.join(ROOT, fn), encoding="utf-8") as f:
            fm, body = split_front_matter(f.read())
        permalink = fm.get("permalink", "/" + fn.replace(".html", "/"))
        prefix = rel_prefix(permalink)
        ctx = {"site": cfg, "prefix": prefix, "page_url": permalink, "page_title": fm.get("title", "")}
        ctx["content"] = resolve_liquid(body, ctx)
        html = resolve_liquid(layout, ctx)
        dest = out_path_for(permalink)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(html)
        built.append(os.path.relpath(dest, ROOT))
    src_assets = os.path.join(ROOT, "assets")
    if os.path.isdir(src_assets):
        shutil.copytree(src_assets, os.path.join(OUT, "assets"), dirs_exist_ok=True)
    print("Built %d pages into %s" % (len(built), OUT))
    for b in sorted(built):
        print("  ", b)
    print("\nOpen this in a browser:\n  ", os.path.join(OUT, "index.html"))

if __name__ == "__main__":
    main()
