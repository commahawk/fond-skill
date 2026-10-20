---
title: Griddle Night
lineage:
  origin: composed
  made_on: 2026-10-13
  changes:
    - composed by the assistant from the user's description
    - merge the two rest countdowns into one ~rest{15%min}
    - count=2 on griddle-the-cakes, two cakes tonight
    - split sear-the-steak -> sear-the-first-side, sear-the-second-side
    - retitle Blanch the Greens as Blanch the Rabe
    - add ~boil{6%min} on boil-the-water
---
# Griddle Night

## Rest the Batter [phase=prep section=cakes duration=15 attention_level=none]
Rest the @batter{1 batch corn cake batter}, ~rest{15%min}.

## Toast the Spices [phase=prep section=steak duration=2 attention_level=high]
Toast the @cumin{1 tsp cumin seeds} in a dry skillet until fragrant, ~toast{2%min}.

## Boil the Water [phase=prep section=greens duration=6 attention_level=low]
Bring a pot of @water{2 quarts water} to a rolling boil, ~boil{6%min}.

## Sear the First Side [phase=cook section=steak duration=2 attention_level=high depends_on=[toast-the-spices]]
Sear the @steak{1 strip steak} in the hot skillet on the first side, ~sear{2%min}.

## Sear the Second Side [phase=cook section=steak duration=2 attention_level=high depends_on=[sear-the-first-side]]
Flip the steak and sear the second side, ~sear{2%min}.

## Griddle the Cakes [phase=cook section=cakes duration=3 attention_level=medium count=2 depends_on=[rest-the-batter]]
Cook each cake until bubbles form, ~cook{3%min}.

## Blanch the Rabe [phase=cook section=greens duration=2 attention_level=medium depends_on=[boil-the-water]]
Blanch the @greens{1 bunch broccoli rabe}(trimmed) in the boiling water and drain.

## Plate the Supper [phase=serve section=steak duration=2 attention_level=full depends_on=[sear-the-second-side, griddle-the-cakes, blanch-the-rabe]]
Slice the steak and plate it with the cakes and greens.
