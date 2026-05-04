
# EDA Findings — Credit Card Fraud Dataset

## Dataset
- 284,807 transactions, 31 columns (Time, V1-V28, Amount, Class).
- V1-V28 are PCA-transformed features (anonymized for privacy).
- Time is seconds since the first transaction in the dataset.
- Amount is the transaction value in euros.
- Class: 1 = fraud, 0 = legit.

## Class imbalance
- Fraud rate: 0.1727% (492 fraud / 284,315 legit).
- Severely imbalanced. Accuracy is a useless metric here.
- Modeling implications:
    * Use Precision-Recall AUC (PR-AUC) or F1 instead of accuracy.
    * Use class weighting in the model (scale_pos_weight in XGBoost).
    * Use stratified train/test splits to keep fraud rate balanced across folds.

## Time patterns
- The 'time' column is seconds since the first transaction; we derived 'hour'.
- Fraud rate varies materially by hour of day (peaks visible in plot).
- 'hour' will be a feature worth engineering.

## Amount patterns
- Heavy-tailed distribution; log-transform recommended.
- Fraud transactions skew toward smaller amounts on average.

## Feature signal
- Top correlated features with class (absolute value):
  V14, V12, V10, V17, V11.
- These will dominate any tree-based model.
- Most V features have weak individual correlation but can still
  contribute to a tree ensemble through interactions.

## Data quality
- No missing values.
- All numeric features convert cleanly to double.
- Class is binary {0, 1}.

## Decisions for downstream phases
- Engineer hour-of-day from 'time'.
- Engineer log_amount.
- Drop 'time' itself (it's a synthetic count, not a real timestamp).
- Convert to Parquet for the processed zone (proper types, columnar, fast).
- Use stratified split for train/test in Phase 3.
- Use scale_pos_weight ≈ 577 (= legit_count / fraud_count) in XGBoost.
- Optimize PR-AUC; threshold-tune for business cost trade-off (FN >> FP).
