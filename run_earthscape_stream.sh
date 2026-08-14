#!/bin/bash
set -e
H=/home/wardastudio/hadoop
export HADOOP_HOME="$H"
export HADOOP_CONF_DIR="$H/etc/hadoop"
export PATH="$H/bin:$H/sbin:$PATH"
WORK=/mnt/c/Users/Dell/Downloads/EarthScape
JAR="$H/share/hadoop/tools/lib/hadoop-streaming-3.3.6.jar"
LOCAL_DATA="$WORK/data/weather_raw.csv"
HDFS_INPUT_DIR=/user/wardastudio/input
INPUT="$HDFS_INPUT_DIR/weather_raw.csv"
OUTPUT=/user/wardastudio/output_earthscape_test
cd "$WORK"
"$H/bin/hdfs" dfs -mkdir -p "$HDFS_INPUT_DIR"
"$H/bin/hdfs" dfs -put -f "$LOCAL_DATA" "$INPUT"
"$H/bin/hdfs" dfs -test -e "$INPUT"
"$H/bin/hdfs" dfs -rm -r -skipTrash "$OUTPUT" || true
"$H/bin/hadoop" jar "$JAR" \
  -D mapreduce.job.name=EarthScapeTest \
  -D mapreduce.am.java.opts="-Xmx1024m --add-opens=java.base/java.lang=ALL-UNNAMED" \
  -files hadoop/mapper.py,hadoop/reducer.py \
  -mapper "python3 mapper.py" \
  -reducer "python3 reducer.py" \
  -input "$INPUT" \
  -output "$OUTPUT"
"$H/bin/hdfs" dfs -ls "$OUTPUT"
"$H/bin/hdfs" dfs -cat "$OUTPUT/part-*" | head -50
