#!/bin/bash
set -ex
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
H=/home/wardastudio/hadoop
export HADOOP_HOME="$H"
export HADOOP_CONF_DIR="$H/etc/hadoop"
export PATH="$H/bin:$H/sbin:$PATH"
cd /mnt/c/Users/Dell/Downloads/EarthScape
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf 'HADOOP_HOME=%s\n' "$HADOOP_HOME"
which hdfs || true
which hadoop || true
hdfs version | head -5
hdfs dfs -ls / || true
echo RC_ROOT=$?
hdfs dfs -ls /user || true
echo RC_USER=$?
hdfs dfs -ls /user/wardastudio || true
echo RC_USERDIR=$?
hdfs dfs -ls /user/wardastudio/input || true
echo RC_INPUTDIR=$?
hdfs dfs -test -e /user/wardastudio/input/weather_raw.csv
RC_EXIST=$?
echo TEST_EXIT=$RC_EXIST
