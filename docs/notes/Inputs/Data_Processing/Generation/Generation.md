# Generation.py — notes

Background pulled out of `Inputs/Data_Processing/Generation/Generation.py` to keep the module itself short.

## Overview

Generation cleaning — mirrors demand pipeline conventions. Energy-from-the-
start: MW x dt integration, never mean-of-means. Valid day: span >= 23h AND
max gap <= 20 min.
