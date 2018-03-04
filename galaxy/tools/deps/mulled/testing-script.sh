#!/bin/sh

set -e

mulled-search --destination docker conda github singularity --search vsearch
mulled-search --destination docker --organization coreos --search hyperkube --json --non-strict
mulled-search --destination conda --channel conda-forge --search mayavi

mulled-update-singularity-containers --containers abundancebin:1.0.1--0 --filepath . --installation singularity
mulled-singularity-testing --containers abundancebin:1.0.1--0 --filepath . --installation singularity

mulled-update-conda-envs -e abundancebin:1.0.1--0 -f /tmp/envs
mulled-update-conda-envs -e abundancebin:1.0.1--0 -o /tmp/conda.log

mulled-list -s docker --not-singularity -f /tmp/foutput.txt
