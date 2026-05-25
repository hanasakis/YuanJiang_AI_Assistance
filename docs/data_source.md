# Olist Dataset — Data Source Documentation

## Source

| Field | Value |
|-------|-------|
| **Dataset** | Brazilian E-Commerce Public Dataset by Olist |
| **Origin** | Kaggle |
| **URL** | https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce |
| **Publisher** | Olist (Brazilian e-commerce platform) |
| **License** | CC BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike) |
| **Version** | v9 (latest public release) |
| **Size** | ~120 MB uncompressed, 9 CSV files |
| **Time Range** | 2016-09 to 2018-10 |

## License & Usage Restrictions

- **CC BY-NC-SA 4.0** means:
  - **Attribution**: Must credit Olist as the data source
  - **Non-Commercial**: Cannot use this dataset for commercial purposes without Olist's permission
  - **Share-Alike**: Derivative works must use the same license
- This project uses the dataset for **educational and non-commercial inspection tool development**
- Customer PII is already anonymized by Olist (no real names, addresses, or payment details)

## Dataset Schema (9 Tables)

### 1. orders (`olist_orders_dataset.csv`) — ~99,441 rows

| Column | Type | Description |
|--------|------|-------------|
| order_id | VARCHAR | Unique order identifier |
| customer_id | VARCHAR | FK → customers.customer_id |
| order_status | VARCHAR | delivered, shipped, canceled, unavailable, etc. |
| order_purchase_timestamp | TIMESTAMP | When the order was placed |
| order_approved_at | TIMESTAMP | When payment was approved |
| order_delivered_carrier_date | TIMESTAMP | When handed to logistics carrier |
| order_delivered_customer_date | TIMESTAMP | When delivered to customer |
| order_estimated_delivery_date | TIMESTAMP | Original delivery promise |

### 2. order_items (`olist_order_items_dataset.csv`) — ~112,650 rows

| Column | Type | Description |
|--------|------|-------------|
| order_id | VARCHAR | FK → orders.order_id |
| order_item_id | INTEGER | Line item sequence number (1, 2, ...) |
| product_id | VARCHAR | FK → products.product_id |
| seller_id | VARCHAR | FK → sellers.seller_id |
| shipping_limit_date | TIMESTAMP | Seller's shipping deadline |
| price | DECIMAL | Unit price (BRL) |
| freight_value | DECIMAL | Shipping cost (BRL) |

### 3. order_payments — ~103,886 rows

| Column | Type | Description |
|--------|------|-------------|
| order_id | VARCHAR | FK → orders.order_id |
| payment_sequential | INTEGER | Payment installment number |
| payment_type | VARCHAR | credit_card, boleto, voucher, debit_card |
| payment_installments | INTEGER | Number of installments |
| payment_value | DECIMAL | Transaction amount (BRL) |

### 4. order_reviews — ~99,223 rows (one per review)

| Column | Type | Description |
|--------|------|-------------|
| review_id | VARCHAR | Unique review identifier |
| order_id | VARCHAR | FK → orders.order_id |
| review_score | INTEGER | 1 (worst) to 5 (best) |
| review_comment_title | VARCHAR | Review title (may be empty) |
| review_comment_message | VARCHAR | Review body (may be empty) |
| review_creation_date | TIMESTAMP | When review was written |
| review_answer_timestamp | TIMESTAMP | When seller responded |

### 5. products — ~32,951 rows

| Column | Type | Description |
|--------|------|-------------|
| product_id | VARCHAR | Unique product identifier |
| product_category_name | VARCHAR | Category in Portuguese |
| product_name_lenght | INTEGER | Length of product name (characters) |
| product_description_lenght | INTEGER | Length of description (characters) |
| product_photos_qty | INTEGER | Number of product photos |
| product_weight_g | INTEGER | Weight in grams |
| product_length_cm | INTEGER | Length in cm |
| product_height_cm | INTEGER | Height in cm |
| product_width_cm | INTEGER | Width in cm |

### 6. sellers — ~3,095 rows

| Column | Type | Description |
|--------|------|-------------|
| seller_id | VARCHAR | Unique seller identifier |
| seller_zip_code_prefix | VARCHAR | First 5 digits of ZIP |
| seller_city | VARCHAR | Seller city |
| seller_state | VARCHAR | Seller state (2-letter code) |

### 7. customers — ~99,441 rows

| Column | Type | Description |
|--------|------|-------------|
| customer_id | VARCHAR | Unique customer identifier |
| customer_unique_id | VARCHAR | Deduplicated customer key |
| customer_zip_code_prefix | VARCHAR | First 5 digits of ZIP |
| customer_city | VARCHAR | Customer city |
| customer_state | VARCHAR | Customer state (2-letter code) |

### 8. geolocation — ~1,000,163 rows

| Column | Type | Description |
|--------|------|-------------|
| geolocation_zip_code_prefix | VARCHAR | 5-digit ZIP prefix |
| geolocation_lat | DOUBLE | Latitude |
| geolocation_lng | DOUBLE | Longitude |
| geolocation_city | VARCHAR | City name |
| geolocation_state | VARCHAR | State code |

### 9. category_translation — 71 rows

| Column | Type | Description |
|--------|------|-------------|
| product_category_name | VARCHAR | Category name (Portuguese) |
| product_category_name_english | VARCHAR | Category name (English) |

## Analytical Views

The DuckDB database creates four views for the inspection agent:

| View | Purpose | Key Metrics |
|------|---------|-------------|
| `orders_enriched` | Orders with all context | delivery_delay_days, total_payment, review_score |
| `seller_delivery_metrics` | Seller delivery performance | avg_delivery_delay, delay_rate_pct, cancel_rate_pct |
| `review_risk_metrics` | Seller review risk | avg_review_score, negative_review_rate_pct |
| `product_quality_metrics` | Product quality signals | defect_rate_pct, avg_review_score per product |

## Why Record Data Provenance

1. **Legal compliance**: CC BY-NC-SA 4.0 requires attribution. If we deploy
   this tool, we must be able to prove the data's license allows our use case.

2. **Reproducibility**: A future developer (or your future self) must know
   exactly which dataset version and preprocessing steps produced the
   analysis results. "Downloaded from Kaggle sometime in 2024" is useless;
   "v9, downloaded 2026-05-26, SHA256 verified" is actionable.

3. **Audit trail**: If an inspection result is challenged ("Why did the
   Agent flag seller X?"), the data provenance chain lets you trace back
   from the flag → the metric → the source row → the dataset version.
