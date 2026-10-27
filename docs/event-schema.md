# Unified shopping events

The current product/data-only demo shows catalog products without calling AI.
Recommendation endpoints have been removed. The event contract below
is unchanged; simulated history and browser tracking use these shopping events.

Here, catalog means the product inventory, not interest tags. Product tags such
as gaming/performance and user occupations/personas are removed; product types
and brands remain. Fresh startup creates no behavioral history. See
[startup](startup.md) for the isolated experiment dataset.

## Event fields

| Fields | Purpose |
| --- | --- |
| event_id, timestamp | Unique event ID and timezone-aware occurrence time |
| distinct_id, session_id | Visitor and browsing session |
| event_name | product_impression, product_click, product_view, search, add_to_wishlist, add_to_cart, remove_from_cart, purchase |
| product_id, query | Product or search text |
| order_id, order_item_id | Order and purchased line item |
| page | home, catalog, search, product_detail, cart |
| list_id | One rendered list; regenerated when its contents reload |
| position | Actual displayed position, starting at 1 |
| request_id | Optional technical request trace |
| source, synthetic, environment, consent, bot | Origin and analytics eligibility |

Display context is optional for historical/simulator compatibility. Home and
catalog cards supply all three fields. Impressions fire once per mounted
card/list when at least 50% is visible. Clicks reuse the same list ID.

```json
{
  "event_id": "43c47198-d555-4efb-9caa-1a1029b8a381",
  "timestamp": "2026-10-27T03:00:00Z",
  "distinct_id": "U0001",
  "session_id": "session-01",
  "event_name": "product_click",
  "product_id": "P0001",
  "page": "home",
  "list_id": "list-01",
  "position": 3,
  "source": "website",
  "synthetic": true,
  "environment": "dev",
  "consent": false,
  "bot": false
}
```

## Normalization and metrics

Normalization unwraps PostHog properties and standardizes user/time/query fields.
Only the shopping event contract above is supported. Raw data is retained;
rerun the pipeline to regenerate derived datasets.

`/internal/metrics` exposes `product_list_ctr`: matched unique visitor/list/product
clicks divided by unique exposures. Events without list_id are excluded.
This measures shopping-list interactions, not model quality or causal conversions.
