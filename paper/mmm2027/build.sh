#!/usr/bin/env bash
# Build the supplied manuscript and bibliography without shell escape.
set -euo pipefail
cd -- "$(dirname -- "$0")"
# Normally TeX Live or MiKTeX already supplies these paths and the XeLaTeX format.
# This fallback also supports a minimal Debian/Ubuntu TeX Live installation.
if ! kpsewhich article.cls >/dev/null 2>&1 && [[ -d /usr/share/texlive/texmf-dist ]]; then
  export TEXMF='{.,/usr/share/texlive/texmf-dist,/usr/share/texmf}'
fi
cache="$PWD/.build-cache"
mkdir -p "$cache"
export XDG_CACHE_HOME="$cache"
export SOURCE_DATE_EPOCH=1793473200 FORCE_SOURCE_DATE=1 TZ=UTC
if ! kpsewhich xelatex.fmt >/dev/null 2>&1; then
  export TEXFORMATS="$cache:"
  if [[ ! -s "$cache/xelatex.fmt" ]]; then
    ini="$(kpsewhich xelatex.ini)"
    (cd "$cache" && xetex -ini -etex -no-shell-escape -interaction=nonstopmode \
      -halt-on-error -jobname=xelatex -progname=xelatex "$ini" > format-build.log 2>&1)
  fi
fi
xelatex -no-shell-escape -no-pdf -interaction=nonstopmode -halt-on-error main.tex
bibtex main
xelatex -no-shell-escape -no-pdf -interaction=nonstopmode -halt-on-error main.tex
xelatex -no-shell-escape -no-pdf -interaction=nonstopmode -halt-on-error main.tex
# Standard TeX Live font maps: newtx for the text/math and fallback symbols.
xdvipdfmx -f newtx.map -f lm-ec.map -f lm-ts1.map -f lm-math.map \
  -f cm.map -f cmextra.map -f euler.map -f latxfont.map -o main.pdf main.xdv
