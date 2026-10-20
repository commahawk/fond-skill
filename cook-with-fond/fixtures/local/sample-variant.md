---
title: Skillet Steak Supper
author: "@ana"
source_url: https://blog.example/skillet-steak-supper
attribution:
  - source Cara
lineage:
  origin: variant
  parent_id: rcp-steak-01
  parent_handle: skillet-steak-supper-a1b2c3
  parent_lineage: forked from rcp-parent-77 at v2; credits @cara, @ben
  exported_at: 2026-10-08T12:00:00+00:00
  credits:
    - cara
    - ben
  made_on: 2026-10-13
  changes:
    - copied from the Fond-format steps the export carries
    - set duration=2 on toast-the-spices, the sigil total
    - set duration=15 on rest-the-dough, the sigil total
    - set duration=4 on sear-the-steak, the sigil total
    - set duration=25 on reduce-the-glaze, the sigil total
    - set duration=3 on griddle-the-corn-cakes, the sigil total
    - rename blanch-the-greens -> blanch-the-rabe
    - split sear-the-steak -> sear-the-first-side, sear-the-second-side
    - add ~preheat{15%min} on preheat-the-oven
---
# Skillet Steak Supper

## Preheat the Oven [phase=prep section=sides duration=15 attention_level=none]
Preheat the oven to 325°F, ~preheat{15%min}.

## Boil the Water [phase=prep section=greens duration=6 attention_level=low]
Bring a large pot of @water{2 quarts water} to a rolling boil.

## Toast the Spices [phase=prep section=sauce duration=2 attention_level=high]
Toast the @cumin{1 tsp cumin seeds} in a dry skillet until fragrant, ~toast{2%min}.

## Rest the Dough [phase=prep section=bread duration=15 attention_level=none]
Rest the @dough{1 ball flatbread dough}, ~rest{5%min, 10%min}.

## Sear the First Side [phase=cook section=main duration=2 attention_level=high depends_on=[toast-the-spices]]
Sear the @steak{1 strip steak} in the hot skillet on the first side, ~sear{2-3%min}.

## Sear the Second Side [phase=cook section=main duration=2 attention_level=high depends_on=[sear-the-first-side]]
Flip the steak and sear the second side, ~sear{2-3%min}.

## Simmer the Sauce [phase=cook section=sauce duration=22 attention_level=low depends_on=[sear-the-second-side]]
Simmer the @stock{1 cup chicken stock} with the pan drippings and the toasted @cumin, covered, ~simmer{20%min}.

## Reduce the Glaze [phase=cook section=sauce duration=25 attention_level=low depends_on=[simmer-the-sauce]]
Simmer, uncovered, until syrupy, ~simmer{25%min}.

## Cook the Flatbreads [phase=cook section=bread duration=4 attention_level=medium count=2 depends_on=[rest-the-dough]]
Cook each flatbread in a dry pan until puffed, ~cook{3%min}.

## Griddle the Corn Cakes [phase=cook section=sides duration=3 attention_level=medium count=3]
Cook each @corn-cake{1 batch corn cake batter} until bubbles form, ~cook{3%min}.

## Blanch the Rabe [phase=cook section=greens duration=2 attention_level=medium depends_on=[boil-the-water]]
Blanch the @greens{1 bunch broccoli rabe}(trimmed) in the boiling water and drain.

## Roast the Vegetables [phase=cook section=sides duration=25 attention_level=none depends_on=[preheat-the-oven]]
Roast the @carrots{3 carrots}(cut into batons) on a tray, ~roast{25%min}.

## Plate the Supper [phase=serve section=main duration=3 attention_level=full depends_on=[reduce-the-glaze, cook-the-flatbreads, griddle-the-corn-cakes, blanch-the-rabe, roast-the-vegetables]]
Slice the steak, spoon the glaze over it and plate with the flatbreads, corn cakes, greens and carrots.
