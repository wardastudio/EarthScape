# EarthScape Hadoop MapReduce

This package contains a Hadoop Streaming-compatible MapReduce pipeline for EarthScape climate aggregation.

## What it does

The pipeline processes `data/weather_raw.csv` (or any CSV file with the same weather metric columns) and computes climate statistics grouped by derived `WeatherCondition`, plus an overall `ALL` aggregate.

## Mapper responsibilities

- Read CSV from standard input
- Skip the header row
- Parse required climate columns using Python CSV parsing
- Derive `WeatherCondition` when it is not present in the source data
- Skip malformed rows, missing values, and invalid numeric values without crashing
- Emit tab-separated key/value pairs using JSON values
- Emit one record for the row's `WeatherCondition` group and one record for `ALL`

## Reducer responsibilities

- Read mapper output from standard input
- Group records by key
- Aggregate statistics for each group
- Emit a JSON summary line for each group
- Maintain counts for:
  - average temperature
  - average humidity
  - total and average rainfall
  - average wind speed
  - average AQI
  - average CO2
  - average carbon emission
  - flood risk counts
  - heatwave counts
  - average climate severity

## Aggregation key

The pipeline groups by `WeatherCondition` because the current dataset does not contain geographic coordinates or temporal partition keys.

This means the implementation is honest about the dataset's limitations: it provides useful condition-level climate aggregation, but it does not perform true spatial partitioning.

## Running locally without Hadoop

EarthScape includes a local fallback that runs the same mapper/reducer logic without Hadoop.

```bash
python -m pytest tests/test_hadoop.py -q
```

## Running with Hadoop Streaming

If Hadoop is available, the service will attempt real Hadoop Streaming execution.

Set one or both environment variables:

- `HADOOP_HOME` (to locate the Hadoop binary and streaming jar)
- `HADOOP_STREAMING_JAR` (explicit path to `hadoop-streaming.jar`)

Then the `POST /api/hadoop/process` endpoint will try to execute:

```bash
hadoop jar <streaming_jar> -files mapper.py,reducer.py -mapper "python3 mapper.py" -reducer "python3 reducer.py" -input <dataset> -output <output_dir>
```

## Limitations

- The current dataset has no latitude/longitude or timestamp fields used for partitioning.
- Therefore the MapReduce pipeline groups by `WeatherCondition` only.
- The `ALL` aggregate provides overall climate statistics.
