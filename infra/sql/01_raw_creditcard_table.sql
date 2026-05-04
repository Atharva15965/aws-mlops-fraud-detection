-- Phase 1: Raw zone table for credit card fraud dataset
-- Uses OpenCSVSerde to handle quoted/scientific-notation values in source CSV.
-- All columns declared STRING (OpenCSVSerde limitation); CAST at query time.

DROP TABLE IF EXISTS mlops_fraud_detection.raw_creditcard;

CREATE EXTERNAL TABLE mlops_fraud_detection.raw_creditcard (
  time   string, v1 string, v2 string, v3 string, v4 string,
  v5 string, v6 string, v7 string, v8 string, v9 string,
  v10 string, v11 string, v12 string, v13 string, v14 string,
  v15 string, v16 string, v17 string, v18 string, v19 string,
  v20 string, v21 string, v22 string, v23 string, v24 string,
  v25 string, v26 string, v27 string, v28 string,
  amount string, class string
)
PARTITIONED BY (year string, month string, day string)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  'separatorChar' = ',',
  'quoteChar'     = '"',
  'escapeChar'    = '\\'
)
STORED AS TEXTFILE
LOCATION 's3://REPLACE_WITH_BUCKET_NAME/raw/creditcard/'
TBLPROPERTIES ('skip.header.line.count' = '1');

MSCK REPAIR TABLE mlops_fraud_detection.raw_creditcard;
