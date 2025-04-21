# mdindex

Simple script to create table of contents within index collection of markdown
files. This creates both in-file table of contents as well as index files
linking out to their siblings and children. It's mostly useful to navigate
documentation that ends up on GitHub / Gitlab / etc as the primary consumption
UI.

This exist because I keep needing variations of it and existing solutions I've
tried never tick all the boxes so I've ended up with N versions floating around
and I want a single one.

Among other issues the main driver that made me write this multiple times are:

- Need to handle both inline table of contents and index files. There's a lot of
  good inline TOC generators (incl. VSCode extension) but I more often than not
  start from needing index files.
- Deal with codeblocks properly
- Not choke on badly structured files with inconsistent headings
- Deal with ATX and settext headers properly even when mixed
- Not assume everything has an H1/H2 and have a decent default re. where to
  upset the TOC

Also extracting it means I now have some tests and basic lints in place.

Some notes:

- Performance is not a priority, and the code could be optimised if really
  required (but also Python ¯\_(ツ)_/¯). It's likely to be good enough for the
  common use case of under a few hundered files and there's probably a few low
  hanging fruits to pick up if I really cared.
- It's likely missing some edge case as I didn't want to bring in a markdown
  parser / the various iterations of this over time have been inlined and so
  being no dependencies was an advantage.
