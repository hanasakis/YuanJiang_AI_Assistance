# YuanJiang OpsGuard — Evaluation Report

**Date**: 2026-05-27
**Questions**: 32
**Duration**: 3.9s

## Summary Metrics

| Metric | Score | Description |
|--------|-------|-------------|
| Intent Accuracy | **59.4%** | Correctly classifies user intent into 5 categories |
| Metric Tool Success | **100.0%** | Data queries return valid structured results |
| SOP Source Hit Rate | **54.5%** | SOP retrieval finds the expected document |
| Task Creation Success | **100.0%** | Task creation requests produce valid tasks |

## By Difficulty

| Difficulty | Count | Intent Accuracy |
|------------|-------|-----------------|
| easy | 15 | 53.3% |
| medium | 11 | 72.7% |
| hard | 6 | 50.0% |

## By Intent

| Intent | Count | Accuracy |
|--------|-------|----------|
| metric_query | 9 | 55.6% |
| sop_qa | 9 | 66.7% |
| create_task | 4 | 75.0% |
| mixed | 8 | 37.5% |
| unknown | 2 | 100.0% |

## Detailed Results

| ID | Question | Expected | Actual | Intent OK | Metric | SOP | Task |
|----|----------|----------|--------|-----------|--------|-----|------|
| eval_001 | Show top 5 sellers with highest delay rate... | metric_query | sop_qa | FAIL | OK | HIT | OK |
| eval_002 | What is the P0 threshold for delivery delay?... | sop_qa | sop_qa | OK | OK | HIT | OK |
| eval_003 | Create a P0 inspection task for seller_A due to de... | create_task | create_task | OK | OK | MISS | OK |
| eval_004 | Check seller_A delay rate, if >30% create P0 task ... | mixed | mixed | OK | OK | MISS | OK |
| eval_005 | List sellers with delay_rate > 20% and cancel_rate... | metric_query | metric_query | OK | OK | HIT | OK |
| eval_006 | How should I handle a seller with 25% delay rate?... | sop_qa | sop_qa | OK | OK | HIT | OK |
| eval_007 | Create a quality inspection task for product prod_... | create_task | create_task | OK | OK | HIT | OK |
| eval_008 | Show me the detailed profile for seller_A includin... | metric_query | metric_query | OK | OK | HIT | OK |
| eval_009 | What is the negative review triage flow for a sell... | mixed | metric_query | FAIL | OK | MISS | OK |
| eval_010 | Tell me a joke... | unknown | unknown | OK | OK | HIT | OK |
| eval_011 | Which product categories have the highest defect r... | metric_query | metric_query | OK | OK | HIT | OK |
| eval_012 | According to SOP, what actions should be taken whe... | sop_qa | sop_qa | OK | OK | HIT | OK |
| eval_013 | Create P1 review_triage task for seller_B with 10 ... | create_task | create_task | OK | OK | MISS | OK |
| eval_014 | What is the SLA for resolving a P0 inspection task... | sop_qa | unknown | FAIL | OK | HIT | OK |
| eval_015 | Show all open inspection tasks sorted by priority... | metric_query | mixed | FAIL | OK | HIT | OK |
| eval_016 | Review seller_C metrics: delay_rate=28%, low_revie... | mixed | create_task | FAIL | OK | MISS | OK |
| eval_017 | What is the procedure for exempting a seller from ... | sop_qa | sop_qa | OK | OK | HIT | OK |
| eval_018 | Find orders where delivery_delay_days > 7 and revi... | metric_query | metric_query | OK | OK | HIT | OK |
| eval_019 | Close task YJ-20260527-0001 as resolved with note ... | create_task | metric_query | FAIL | OK | HIT | OK |
| eval_020 | What is the weather today?... | unknown | unknown | OK | OK | HIT | OK |
| eval_021 | Compare delay rates of sellers in SP state vs RJ s... | metric_query | metric_query | OK | OK | HIT | OK |
| eval_022 | What does SOP say about handling seasonal return s... | sop_qa | sop_qa | OK | OK | HIT | OK |
| eval_023 | Check electronics category quality, if defect_rate... | mixed | mixed | OK | OK | MISS | OK |
| eval_024 | Show me the order details for ord_002 and explain ... | mixed | metric_query | FAIL | OK | MISS | OK |
| eval_025 | What is the task status flow from pending to close... | sop_qa | unknown | FAIL | OK | HIT | OK |
| eval_026 | Create a delivery_risk task for seller_D, priority... | mixed | create_task | FAIL | OK | HIT | OK |
| eval_027 | List all P0 and P1 tasks created today... | metric_query | create_task | FAIL | OK | HIT | OK |
| eval_028 | What is the threshold for escalating a review_tria... | sop_qa | sop_qa | OK | OK | MISS | OK |
| eval_029 | Analyze seller_A: show delay metrics, SOP assessme... | mixed | mixed | OK | OK | MISS | OK |
| eval_030 | Show total count and breakdown of tasks by status ... | metric_query | mixed | FAIL | OK | HIT | OK |
| eval_031 | What is the maximum allowed response time for a P0... | sop_qa | unknown | FAIL | OK | HIT | OK |
| eval_032 | For seller_B with delivery_rate 22% and low review... | mixed | create_task | FAIL | OK | MISS | OK |