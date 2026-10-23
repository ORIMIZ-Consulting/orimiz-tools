# Methodology

This note explains how the FEL1 LNG Cost tool turns past project costs into a cost range for a new project. Each step is simple on purpose, so that a reviewer can check it by hand.

## 1. Which analogues are used

The tool keeps analogues that match:

- the **facility type** you chose (onshore liquefaction, FLNG, onshore regas or FSRU),
- the **scopes** you allow (by default "plant only" and "plant plus pipeline"), and
- your own choice in the analogue table, where you can untick any project.

Costs are first converted to US dollars with the `fx_to_usd` rate stored in each row, at the rate of the cost year.

## 2. Escalation

Costs from different years must be brought to the same money. The factor from the analogue's year *y₀* to the estimate year *y* is:

- with a constant rate *r*: (1 + *r*)^(*y* − *y₀*)
- with a cost index *I*: *I*(*y*) ÷ *I*(*y₀*)

The default rate is 3% a year. Plant construction costs have often risen faster than general inflation, and not smoothly. Over long periods a published plant cost index is better. The tool does not include one, because most such indices are under copyright. You can upload one you hold.

## 3. Location

Building the same plant costs different amounts in different places: labour rates, productivity, climate, logistics and local rules all differ. You give one factor per region and one for your site, all on the same base. The adjustment is:

target factor ÷ analogue factor

With every factor at 1.00 (the default), there is no adjustment.

## 4. Size

Cost does not rise in step with size. The exponent rule is:

*C* = *C*ₐ × (*Q* ÷ *Q*ₐ)^*n*

where *C*ₐ and *Q*ₐ are the analogue's cost and capacity, *Q* is your capacity, and *n* is the exponent. With *n* = 0.7, doubling capacity raises cost by about 62%, not 100%.

Defaults:

| Facility | *n* |
|---|---|
| Onshore liquefaction | 0.7 |
| FLNG | 0.7 |
| Onshore regas | 0.6 |
| FSRU | 0.6 |

These are common rules of thumb for process plants (the "six-tenths rule" and its variations), not fitted values. The rule is least reliable for large size differences. The tool flags any analogue more than three times larger or smaller than your plant.

For FSRUs, the price depends mostly on the vessel and its storage, and less on regas rate. Size scaling by regas capacity is therefore rough.

## 5. Weighting

Each analogue's weight is the ratio of the smaller to the larger capacity:

*w* = min(*Q* ÷ *Q*ₐ, *Q*ₐ ÷ *Q*)

So a same-size analogue weighs 1.0, and one twice or half the size weighs 0.5.

## 6. The range

The P50 is the **weighted median** of the analogue-based estimates.

The spread of those estimates gives a weighted P10 and P90. But a few similar analogues can agree by chance and suggest false precision. So the tool also applies an accuracy band around the P50, and reports the wider of the two:

- P10 = lower of (analogue P10) and (P50 × (1 + low))
- P90 = higher of (analogue P90) and (P50 × (1 + high))

AACE International Recommended Practice 18R-97 gives a Class 5 estimate an expected range of −20% to −50% on the low side and +30% to +100% on the high side. The default here is −30% and +50%. Choose wider values for unusual projects or weak data.

## 7. What the tool cannot see

- **Scope gaps.** Announced costs rarely list what they include. Read the notes column.
- **Announced versus final cost.** Most figures are from the investment decision. Several projects later overran.
- **Market timing.** Contractor markets were tight in some years and slack in others. Escalation at a constant rate does not capture this.
- **Site specifics.** Soil, marine works, remote location and gas quality can move costs far from any analogue.

## Sources

Each analogue row has a `source_url`. Please check sources before relying on a figure, and add corrections through your own private file or a pull request.
