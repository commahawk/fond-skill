# Your Fond data export

Exported 2026-10-08T12:00:00+00:00 · export version 2

## Profile
- **Handle:** ana
- **Joined:** 2025-03-01T09:00:00+00:00
- **Total cooks:** 6
- **Total recipes:** 3
- **Credits:** 0
- **Earlier anonymous sessions:** —

## Recipes you created (4)

### Skillet Steak Supper

by Cara · on Fond by @ana

- **Published:** 2026-09-20T18:00:00+00:00
- **Public:** yes
- **Fond id:** rcp-steak-01 (handle skillet-steak-supper-a1b2c3)
- **Source:** https://blog.example/skillet-steak-supper

Lineage: forked from rcp-parent-77 at v2; credits @cara, @ben

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

1. Preheat the Oven — Preheat the oven to 325°F. [Timer: 15 min — done when Preheat the Oven — 15 min]
2. Boil the Water — Bring a large pot of [2 quarts water] to a rolling boil. [~6 min]
3. Toast the Spices — Toast the [1 tsp cumin seeds] in a dry skillet until fragrant. [Timer: 2 min — done when fragrant]
4. Rest the Dough — Rest the [1 ball flatbread dough], 5 minutes, then 10 minutes. [Timer: 15 min — done when rested]
5. Sear the Steak — Sear the [1 strip steak] in the hot skillet, 2 to 3 minutes per side, flipping once. [Timer: 2 min × 2 — done when seared per side (×2)] (after step 3)
6. Simmer the Sauce — Simmer the [1 cup chicken stock] with the pan drippings and the toasted cumin, covered. [Timer: 20 min — done when simmered, covered] (after step 5)
7. Reduce the Glaze — Simmer, uncovered, until syrupy. [Timer: 25 min — done when syrupy] (after step 6)
8. Cook the Flatbreads — Cook each flatbread in a dry pan until puffed. [Timer: 3 min × 2 — done when puffed (×2)] (after step 4)
9. Griddle the Corn Cakes — Cook each [1 batch corn cake batter] until bubbles form. [Timer: 3 min × 3 — done when bubbles form (×3)]
10. Blanch the Greens — Blanch the [1 bunch broccoli rabe, trimmed] in the boiling water and drain. [~2 min] (after step 2)
11. Roast the Vegetables — Roast the [3 carrots, cut into batons] on a tray. [Timer: 25 min — done when roasted] (after step 1)
12. Plate the Supper — Slice the steak, spoon the glaze over it and plate with the flatbreads, corn cakes, greens and carrots. [~3 min] (after step 7, 8, 9, 10, 11)

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

by @ana

- **Published:** 2026-08-15T19:30:00+00:00
- **Public:** yes
- **Fond id:** rcp-pasta-02 (handle weeknight-garlic-pasta-d4e5f6)
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

1. Prep: Slice the garlic — Thinly slice the [garlic]. [~2 min]
2. Prep: Grate the cheese — Grate the [parmesan] and set it aside.
3. Boil the water — Bring a large pot of [water] to a boil and salt it well. [Done when: the water is at a rolling boil]
4. Cook the pasta — Drop the [spaghetti] in and stir once. [Timer: 12 min — done when al dente] (after step 3)
5. Sizzle the garlic — Warm the [olive oil] with the sliced garlic over low heat. [Timer: 0.5 min — done when fragrant] (after step 1)
6. Toss the pasta — Toss the drained pasta with the oil, the [parsley] and a pinch of [chili flakes]. [~8 min] (after step 4, 5)
7. Puff the flatbreads — Toast each [flatbread] in a dry pan until puffed. [Timer: 1 min × 2 — done when puffed (×2)]
8. Fry the eggs — Fry the [eggs] one at a time in the garlic oil. [~2 min × 3] (after step 5)
9. Serve — Plate the pasta with the cheese, a flatbread and an egg each. (after step 6, 7, 8, 2)

### Toast Soldiers

by (unknown)

- **Published:** 2026-07-01T08:00:00+00:00
- **Public:** no
- **Fond id:** rcp-toast-03 (handle toast-soldiers-g7h8i9)

**Ingredients**

- 2 slices bread
- 1 egg
- butter

**Steps**

1. Toast the bread — Toast the [bread] under the grill. [Timer: 3 min — done when golden]
2. Boil the egg — Lower the [egg] into boiling water. [Timer: 6 min — done when set but runny]
3. Serve — Butter the toast with the [butter], cut it into soldiers and serve with the egg. [~1 min] (after step 1, 2)

### Steamed Coconut Rice

by @ana

- **Published:** 2026-06-10T10:00:00+00:00
- **Public:** yes
- **Fond id:** rcp-rice-09 (handle steamed-coconut-rice-w4x5y6)
- **Source:** https://blog.example/coconut-rice

**Ingredients**

- 1 cup jasmine rice
- 1/2 cup coconut flakes
- 1 cup coconut milk
- 1 cup water
- salt

**Steps**

1. Rinse the Rice — Rinse the [1 cup jasmine rice] under cold water until it runs clear. [~3 min]
2. Toast the Coconut — Toast the [1/2 cup coconut flakes] in a dry pan, one batch at a time, until golden. [Timer: 2 min × 2 — done when golden (×2)]
3. Warm the Coconut Milk — Warm the [1 cup coconut milk] with [1 cup water] and a pinch of [salt] until it steams. [~5 min]
4. Simmer the Rice — Add the rice, cover, and simmer over the lowest heat until the liquid is absorbed. [Timer: 15 min — done when the liquid is absorbed] (after step 1, 3)
5. Rest the Rice — Take the pot off the heat and let it rest, covered. [~10 min] (after step 4)
6. Fluff and Serve — Fluff the rice with a fork, scatter the toasted coconut over it and serve. [~2 min] (after step 5, 2)

**Recipe DSL**

```
# Steamed Coconut Rice

## Rinse the Rice [phase=prep section=main duration=3 attention_level=high]
Rinse the @rice{1 cup jasmine rice} under cold water until it runs clear.

## Toast the Coconut [phase=prep section=topping duration=2 attention_level=high count=2]
Toast the @coconut{1/2 cup coconut flakes} in a dry pan, one batch at a time, until golden.

## Warm the Coconut Milk [phase=prep section=main duration=5 attention_level=low]
Warm the @coconut-milk{1 cup coconut milk} with @water{1 cup water} and a pinch of @salt{salt} until it steams.

## Simmer the Rice [phase=cook section=main duration=15 attention_level=none depends_on=[rinse-the-rice, warm-the-coconut-milk]]
Add the rice, cover, and simmer over the lowest heat until the liquid is absorbed.

## Rest the Rice [phase=cook section=main duration=10 attention_level=none depends_on=[simmer-the-rice]]
Take the pot off the heat and let it rest, covered.

## Fluff and Serve [phase=serve section=main duration=2 attention_level=full depends_on=[rest-the-rice, toast-the-coconut]]
Fluff the rice with a fork, scatter the toasted coconut over it and serve.
```

## Recipes you saved (5)

### Tomato Soup

by @ben

- **Saved:** 2026-09-10T08:30:00+00:00 (url)
- **Cooked:** 1×
- **Fond id:** rcp-soup-05 (handle soup-xyz789)
- **Source:** https://blog.example/soup

**Ingredients**

- 1 onion
- 2 tbsp butter
- 1 can tomatoes
- 2 cups stock
- salt

**Steps**

1. Prep: Dice the onion — Dice the [onion]. [~3 min]
2. Sweat the onion — Melt the [butter] and sweat the onion until soft. [~5 min] (after step 1)
3. Simmer the soup — Add the [tomatoes] and the [stock]; simmer. [Timer: 20 min — done when thickened and glossy] (after step 2)
4. Blend and serve — Blend smooth, season with [salt] and serve. [~3 min] (after step 3)

- **Grandma's Stew** by @ben — saved 2026-08-01T12:00:00+00:00 (shared), cooked 1× — https://blog.example/stew
- **Weeknight Garlic Pasta** by @ana — saved 2026-08-16T07:00:00+00:00 (own), cooked 2× — one of your own recipes: see "Weeknight Garlic Pasta" under Recipes you created (Fond id rcp-pasta-02)
- **Old Favourite Curry** by @ben — saved 2026-05-01T12:00:00+00:00 (cooked) — recipe since deleted
- **—** — saved 2026-04-01T12:00:00+00:00 (url)

## Cooking history (6)

### 2026-10-05T17:00:00+00:00 — Sunday supper again (rated) (removed from history)
- Grandma's Stew — completed 2026-10-05T18:20:00+00:00; easy to follow 3/5, taste 2/5, would cook again 1/5

### 2026-10-01T18:00:00+00:00 — Soup night (recorded)
- Tomato Soup — not completed; no rating

### 2026-09-28T17:00:00+00:00 — Sunday supper (rated)
- Grandma's Stew — completed 2026-09-28T18:10:00+00:00; easy to follow 4/5, taste 5/5, would cook again 5/5; feedback: "lovely"

### 2026-09-21T18:00:00+00:00 — Cook (aborted)
- Weeknight Garlic Pasta — not completed (not counted); no rating

### 2026-09-14T18:00:00+00:00 — Weeknight (recorded)
- Tomato Soup — completed 2026-09-14T18:40:00+00:00; taste 4/5, would cook again 4/5
- Weeknight Garlic Pasta — completed 2026-09-14T19:00:00+00:00; easy to follow 5/5, taste 4/5, would cook again 3/5

### 2025-06-01T18:00:00+00:00 — Cook (migrated)
- Weeknight Garlic Pasta — completed 2025-06-01T19:00:00+00:00; easy to follow 4/5

## Contact

_This block is about you alone — delete it before sharing this file._

- **Email:** —
- **Name:** —
- **Phone:** —
- **TikTok:** —
