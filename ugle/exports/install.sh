#!/usr/bin/env bash

# DO NOT TOUCH UNLESS YOU KNOW WHAT YOU ARE DOING
#
# This script installs the dependencies given by 'deps.txt'.
# It requires 'deps.txt' to exist in the folder the script is run from

deps=$(cat deps.txt)
for dep in ${deps//,/ }
do
    # Install the dependencies in order
    dpkg -i $dep
done
