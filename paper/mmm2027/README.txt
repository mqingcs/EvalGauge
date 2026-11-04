EvalGauge camera-ready manuscript source — harmonized 2026-11-01

Base repository: https://github.com/mqingcs/EvalGauge
Base commit: e898565153e0c26ee52ed1c93224bab9afcf32b4
Base manuscript path: paper/mmm2027
Corresponding author: Qing Mu (confirmed by the authors).

Build
  bash build.sh

Requires a complete TeX Live or MiKTeX installation with XeLaTeX/XeTeX,
BibTeX, xdvipdfmx, newtxtext/newtxmath and the packages listed in main.tex.
The stock Springer LNCS class 2.25 (2026-09-03) and splncs04.bst are supplied.
The font configuration follows Springer's sample: T1, newtxtext and
newtxmath[varvw], with babel[english] for standard English hyphenation.
The tested versions are newtxtext 1.744, newtxmath 1.754 and XeTeX 0.999996.
No network, shell escape, experiments or model runs are required.
main.bbl is supplied and is regenerated from references.bib by build.sh.
DescriptionTexts.txt is generated from the native figure descriptions.
The build sets a fixed source-date epoch for reproducible PDF metadata.

Figures
  All three required figures are supplied as embedded-font vector PDFs.
  Figure 1 (fig0_teaser.pdf) and Figure 3 (fig6_public_rescoring.pdf) are
  unchanged from the base repository. Figure 2 (fig1_pipeline.pdf) is the
  revised mechanism drawing for the same clock_64 example. Its typeface is
  now Times-compatible Liberation Serif (union glyph: Nimbus Roman), matching
  the Times-style typography of the retained figures. Fonts are embedded.
  Its editable SVG and generator are in the separate editable-figure ZIP,
  which is not needed to compile the manuscript.

Attribution
  The teaser's instrument crops retain their attribution and license details
  in THIRD_PARTY_NOTICES.md. The new mechanism figure uses an original clock
  schematic, explicitly labeled as such; it uses no external image crop.

Scope
  Scientific claims, results, tables, equations and author order are preserved.
  No reviewer suggestions were adopted and no experiments were run.
  The separate change inventory documents required formatting, bibliography,
  corresponding-author and figure changes, and the minimum abstract expansion.

Layout harmonization
  All table text uses the shared 9 TeX pt LNCS baseline without scaling.
  Table 3 has equal-width panels separated by a standard local medskip.
  Table 1 column padding is slightly increased for clear separation.
  All scientific wording, table cells and reported results are unchanged.
