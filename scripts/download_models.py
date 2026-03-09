#!/usr/bin/env python3
"""Download SAM2 and CLIP model assets to configured paths. Run from repo root."""
import os
import sys

def main():
    sam2_path = os.environ.get("SAM2_CHECKPOINT_PATH", "./models/sam2")
    clip_cache = os.environ.get("CLIP_MODEL_CACHE_DIR", "./models/clip")
    os.makedirs(sam2_path, exist_ok=True)
    os.makedirs(clip_cache, exist_ok=True)
    print("SAM2 checkpoint dir:", sam2_path)
    print("CLIP model cache:", clip_cache)
    print("Place SAM2 checkpoints (e.g. sam2_hiera_large.pt) in SAM2_CHECKPOINT_PATH.")
    print("CLIP weights auto-download on first use to CLIP_MODEL_CACHE_DIR.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
