# Your Fond data export

Exported 2026-10-08T12:00:00+00:00 · export version 1

## Profile
- **Handle:** ana
- **Joined:** 2025-03-01T09:00:00+00:00
- **Total cooks:** 6
- **Total recipes:** 3
- **Credits:** 0
- **Earlier anonymous sessions:** —

## Contact
- **Email:** —
- **Name:** —
- **Phone:** —
- **TikTok:** —

## Recipes you created (3)

### Skillet Steak Supper
- **Handle:** skillet-steak-supper-a1b2c3
- **Published:** 2026-09-20T18:00:00+00:00
- **Public:** yes
- **Source:** https://blog.example/skillet-steak-supper

**Ingredients**

- 2 quarts water
- 1 tsp cumin seeds
- 1 ball flatbread dough
- 1 strip steak
- 1 cup chicken stock
- 1 batch corn cake batter
- 1 bunch broccoli rabe, trimmed
- 3 carrots, cut into batons

**Steps**

1. Preheat the oven to 325°F.
2. Bring a large pot of [2 quarts water] to a rolling boil.
3. Toast the [1 tsp cumin seeds] in a dry skillet until fragrant.
4. Rest the [1 ball flatbread dough], 5 minutes, then 10 minutes.
5. Sear the [1 strip steak] in the hot skillet, 2 to 3 minutes per side, flipping once.
6. Simmer the [1 cup chicken stock] with the pan drippings and the toasted cumin, covered.
7. Simmer, uncovered, until syrupy.
8. Cook each flatbread in a dry pan until puffed.
9. Cook each [1 batch corn cake batter] until bubbles form.
10. Blanch the [1 bunch broccoli rabe, trimmed] in the boiling water and drain.
11. Roast the [3 carrots, cut into batons] on a tray.
12. Slice the steak, spoon the glaze over it and plate with the flatbreads, corn cakes, greens and carrots.

**Recipe DSL**

```
# Skillet Steak Supper

## Preheat the Oven [phase=prep section=sides duration=15 attention_level=none]
Preheat the oven to 325°F.

## Boil the Water [phase=prep section=greens duration=6 attention_level=low]
Bring a large pot of @water{2 quarts water} to a rolling boil.

## Toast the Spices [phase=prep section=sauce attention_level=high]
Toast the @cumin{1 tsp cumin seeds} in a dry skillet until fragrant, ~toast{2%min}.

## Rest the Dough [phase=prep section=bread attention_level=none]
Rest the @dough{1 ball flatbread dough}, ~rest{5%min, 10%min}.

## Sear the Steak [phase=cook section=main attention_level=high depends_on=[toast-the-spices]]
Sear the @steak{1 strip steak} in the hot skillet, ~per-side{2-3%min × 2}, flipping once.

## Simmer the Sauce [phase=cook section=sauce duration=22 attention_level=low depends_on=[sear-the-steak]]
Simmer the @stock{1 cup chicken stock} with the pan drippings and the toasted @cumin, covered, ~simmer{20%min}.

## Reduce the Glaze [phase=cook section=sauce duration=10 attention_level=low depends_on=[simmer-the-sauce]]
Simmer, uncovered, until syrupy, ~simmer{25%min}.

## Cook the Flatbreads [phase=cook section=bread duration=4 attention_level=medium count=2 depends_on=[rest-the-dough]]
Cook each flatbread in a dry pan until puffed, ~cook{3%min}.

## Griddle the Corn Cakes [phase=cook section=sides attention_level=medium count=3]
Cook each @corn-cake{1 batch corn cake batter} until bubbles form, ~cook{3%min}.

## Blanch the Greens [phase=cook section=greens duration=2 attention_level=medium depends_on=[boil-the-water]]
Blanch the @greens{1 bunch broccoli rabe}(trimmed) in the boiling water and drain.

## Roast the Vegetables [phase=cook section=sides duration=25 attention_level=none depends_on=[preheat-the-oven]]
Roast the @carrots{3 carrots}(cut into batons) on a tray, ~roast{25%min}.

## Plate the Supper [phase=serve section=main duration=3 attention_level=full depends_on=[reduce-the-glaze, cook-the-flatbreads, griddle-the-corn-cakes, blanch-the-greens, roast-the-vegetables]]
Slice the steak, spoon the glaze over it and plate with the flatbreads, corn cakes, greens and carrots.
```

### Weeknight Garlic Pasta
- **Handle:** weeknight-garlic-pasta-d4e5f6
- **Published:** 2026-08-15T19:30:00+00:00
- **Public:** yes
- **Source:** https://blog.example/garlic-pasta

**Ingredients**

- garlic
- 300 g spaghetti
- parmesan
- 4 tbsp olive oil
- a handful of parsley
- chili flakes
- 2 flatbreads
- 3 eggs
- water

**Steps**

1. Thinly slice the [garlic].
2. Grate the [parmesan] and set it aside.
3. Bring a large pot of [water] to a boil and salt it well.
4. Drop the [spaghetti] in and stir once.
5. Warm the [olive oil] with the sliced garlic over low heat.
6. Toss the drained pasta with the oil, the [parsley] and a pinch of [chili flakes].
7. Toast each [flatbread] in a dry pan until puffed.
8. Fry the [eggs] one at a time in the garlic oil.
9. Plate the pasta with the cheese, a flatbread and an egg each.

### Toast Soldiers
- **Handle:** toast-soldiers-g7h8i9
- **Published:** 2026-07-01T08:00:00+00:00
- **Public:** no
- **Source:** —

**Ingredients**

- 2 slices bread
- 1 egg
- butter

**Steps**

1. Toast the [bread] under the grill.
2. Lower the [egg] into boiling water.
3. Butter the toast with the [butter], cut it into soldiers and serve with the egg.

## Recipes you saved (5)

- **Tomato Soup** by @ben — saved 2026-09-10T08:30:00+00:00 (url), cooked 1× — https://blog.example/soup
- **Grandma's Stew** by @ben — saved 2026-08-01T12:00:00+00:00 (shared), cooked 1× — https://blog.example/stew
- **Weeknight Garlic Pasta** by @ana — saved 2026-08-16T07:00:00+00:00 (own), cooked 2×
- **Old Favourite Curry** by @ben — saved 2026-05-01T12:00:00+00:00 (cooked) — recipe since deleted
- **—** — saved 2026-04-01T12:00:00+00:00 (url)

## Cooking history (6)

### 2026-10-05T17:00:00+00:00 — Sunday supper again (rated)
- Grandma's Stew — completed 2026-10-05T18:20:00+00:00; easy to follow 3/5, taste 2/5, would cook again 1/5

### 2026-10-01T18:00:00+00:00 — Soup night (recorded)
- Tomato Soup — not completed (not counted); no rating

### 2026-09-28T17:00:00+00:00 — Sunday supper (rated)
- Grandma's Stew — completed 2026-09-28T18:10:00+00:00; easy to follow 4/5, taste 5/5, would cook again 5/5; feedback: "lovely"

### 2026-09-21T18:00:00+00:00 — Cook (aborted)
- Weeknight Garlic Pasta — not completed (not counted); no rating

### 2026-09-14T18:00:00+00:00 — Weeknight (recorded)
- Tomato Soup — completed 2026-09-14T18:40:00+00:00; taste 4/5, would cook again 4/5
- Weeknight Garlic Pasta — completed 2026-09-14T19:00:00+00:00; easy to follow 5/5, taste 4/5, would cook again 3/5

### 2025-06-01T18:00:00+00:00 — Cook (migrated)
- Weeknight Garlic Pasta — completed 2025-06-01T19:00:00+00:00 (not counted); easy to follow 4/5
