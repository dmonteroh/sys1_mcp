#!/usr/bin/env python3
"""Run `jev-style serve` with the MLX buffer cache capped.

MLX keeps freed Metal buffers in a cache that is unbounded by default, which
held the Jev-Style server at about 5.4 GB (peaks 7.5-8 GB on long inputs).
jev-style has no option for it, so set the limit here and hand over to its CLI.
SYS1_MLX_CACHE_LIMIT_BYTES overrides the default of 0 (cache nothing).
"""
import os
import sys

import mlx.core as mx

mx.set_cache_limit(int(os.environ.get("SYS1_MLX_CACHE_LIMIT_BYTES", "0")))

from jev_style.cli import main

sys.exit(main())
