---
title: Griddle Night
lineage:
  origin: composed
  made_on: 2026-10-13
  changes:
    - composed by the assistant from the user's description
---
# Griddle Night

## Rest the Batter [phase=prep section=cakes duration=15 attention_level=none]
Rest the @batter{1 batch corn cake batter}, ~rest{5%min, 10%min}.

## Toast the Spices [phase=prep section=steak duration=2 attention_level=high]
Toast the @cumin{1 tsp cumin seeds} in a dry skillet until fragrant, ~toast{2%min}.

## Boil the Water [phase=prep section=greens duration=6 attention_level=low]
Bring a pot of @water{2 quarts water} to a rolling boil.

## Sear the Steak [phase=cook section=steak duration=4 attention_level=high depends_on=[toast-the-spices]]
Sear the @steak{1 strip steak} in the hot skillet, ~sear{2%min × 2}, flipping once.

## Griddle the Cakes [phase=cook section=cakes duration=3 attention_level=medium count=3 depends_on=[rest-the-batter]]
Cook each cake until bubbles form, ~cook{3%min}.

## Blanch the Greens [phase=cook section=greens duration=2 attention_level=medium depends_on=[boil-the-water]]
Blanch the @greens{1 bunch broccoli rabe}(trimmed) in the boiling water and drain.

## Plate the Supper [phase=serve section=steak duration=2 attention_level=full depends_on=[sear-the-steak, griddle-the-cakes, blanch-the-greens]]
Slice the steak and plate it with the cakes and greens.
