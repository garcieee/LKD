"""Leak-free splits: by time, by group (for example a note family) and by map block. Each returns index arrays."""
import math

import numpy as np


def temporal_split(times, train_end, validation_end) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rows before train_end train, before validation_end validate, the rest test. Times are anything comparable."""
    t = np.asarray(times)
    return np.flatnonzero(t < train_end), np.flatnonzero((t >= train_end) & (t < validation_end)), np.flatnonzero(t >= validation_end)


def group_split(groups, fractions=(0.6, 0.2, 0.2), seed: int = 0) -> tuple[np.ndarray, ...]:
    """Every row of a group lands in one split. Groups are shuffled, then each goes to the split that is furthest
    below its target share of the rows, so the shares come out close even when groups differ in size."""
    g = np.asarray(groups)
    labels, inverse, sizes = np.unique(g, return_inverse=True, return_counts=True)
    order = np.random.default_rng(seed).permutation(len(labels))
    target = np.asarray(fractions, float) / sum(fractions) * len(g)
    filled = np.zeros(len(fractions))
    which = np.empty(len(labels), int)
    for group in order:
        split = int(np.argmax(target - filled))
        which[group] = split
        filled[split] += sizes[group]
    row_split = which[inverse]
    return tuple(np.flatnonzero(row_split == k) for k in range(len(fractions)))


def block_ids(lat, lng, cell_deg: float = 0.02) -> np.ndarray:
    """A grid cell id per point: 0.02 degrees is about 2 km, so nearby points share a block."""
    return np.array([f"{math.floor(a / cell_deg)}:{math.floor(b / cell_deg)}" for a, b in zip(lat, lng)])


def block_split(lat, lng, fractions=(0.6, 0.2, 0.2), cell_deg: float = 0.02, seed: int = 0) -> tuple[np.ndarray, ...]:
    """Split by map block, so a place never appears in two splits. Tests whether a result carries to new places."""
    return group_split(block_ids(lat, lng, cell_deg), fractions, seed)
