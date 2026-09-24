"""Rebuild fine normal maps from the existing crumb texture and seeded noise."""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

textures = Path(__file__).resolve().parents[1] / 'assets/textures'


def save_normal(height, strength, target):
    dy, dx = np.gradient(height)
    normal = np.stack((-dx * strength, -dy * strength, np.ones_like(height)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    Image.fromarray(np.clip((normal * .5 + .5) * 255, 0, 255).astype(np.uint8)).save(target)


crumb = Image.open(textures / 'bread-crumb-v2.png').convert('L').resize((2048, 2048))
height = gaussian_filter(np.asarray(crumb, dtype=np.float32) / 255, 1.2)
save_normal(height, 6, textures / 'bread-micro-normal.png')
rng = np.random.default_rng(2026)
brushed = gaussian_filter(rng.standard_normal((1024, 256)).astype(np.float32), (9, .65))
save_normal(brushed, .52, textures / 'knife-brushed-normal.png')
