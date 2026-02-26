"""Convert MRMS grid data into GeoJSON swath polygons."""

import logging
from datetime import datetime, timezone

import geojson
import numpy as np
from rasterio.features import shapes
from rasterio.transform import Affine
from scipy.ndimage import binary_closing, gaussian_filter
from shapely.geometry import mapping, shape
from shapely.validation import make_valid

logger = logging.getLogger(__name__)

THRESHOLDS_INCHES = [0.50, 0.75, 1.00, 1.50, 2.00]


def grid_to_swaths(
    data: np.ndarray,
    transform: Affine,
    thresholds: list[float],
    product: str = "MESH",
    start_time: str = "",
    end_time: str = "",
    source_files: list[str] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    simplify_tolerance: float = 0.005,
    gaussian_sigma: int = 4,
    min_area_deg2: float = 1e-6,
) -> geojson.FeatureCollection:
    """Convert grid data to GeoJSON swath polygons at the given thresholds.

    Each threshold produces its own set of polygon features.
    All geometries are smoothed, validated, and simplified.

    gaussian_sigma controls edge smoothness (in grid cells, each ~1 km).
    A value of 4 applies ~4 km of smoothing to create organic weather-contour shapes.
    Higher values = smoother but less precise edges.
    """
    if source_files is None:
        source_files = []

    created_at = datetime.now(timezone.utc).isoformat()
    all_features = []

    for threshold in sorted(thresholds, reverse=True):
        features = _polygonize_threshold(
            data=data,
            transform=transform,
            threshold=threshold,
            product=product,
            start_time=start_time,
            end_time=end_time,
            source_files=source_files,
            created_at=created_at,
            bbox=bbox,
            simplify_tolerance=simplify_tolerance,
            gaussian_sigma=gaussian_sigma,
            min_area_deg2=min_area_deg2,
        )
        all_features.extend(features)

    logger.info("Generated %d features across %d thresholds", len(all_features), len(thresholds))
    return geojson.FeatureCollection(all_features)


def _polygonize_threshold(
    data: np.ndarray,
    transform: Affine,
    threshold: float,
    product: str,
    start_time: str,
    end_time: str,
    source_files: list[str],
    created_at: str,
    bbox: tuple[float, float, float, float] | None,
    simplify_tolerance: float,
    gaussian_sigma: int,
    min_area_deg2: float,
) -> list[geojson.Feature]:
    """Polygonize a single threshold and return a list of GeoJSON features."""
    # Step 1: Binary mask — which cells are at or above this threshold?
    mask = data >= threshold
    mask = mask & ~np.isnan(data)

    # Step 2: Morphological cleanup — fill small gaps inside the swath
    mask = binary_closing(mask, structure=np.ones((3, 3)))

    # Step 3: Gaussian blur for smooth organic contours.
    # Blurs the binary (0/1) mask, then re-thresholds at 0.5 to get smooth edges.
    # We then take the UNION with the original binary mask so that small isolated
    # clusters (narrower than ~2*sigma pixels) are never erased — the Gaussian blur
    # alone would reduce their peak below 0.5 and wipe them out entirely.
    #
    # Example: sigma=4 blurs across ~4 grid cells (~4 km).
    #   Large clusters:  smooth organic contour edges (from Gaussian)
    #   Small clusters:  preserved as-is from the original mask (no data loss)
    if gaussian_sigma > 0:
        original_mask = mask.copy()
        blurred = gaussian_filter(mask.astype(np.float32), sigma=gaussian_sigma)
        smooth_mask = blurred >= 0.5
        # Union: keep every pixel from the smooth result AND the original mask
        mask = (smooth_mask | original_mask).astype(np.uint8)
    else:
        mask = mask.astype(np.uint8)

    if mask.sum() == 0:
        return []

    # Step 4: Polygonize the smoothed mask into vector shapes
    features = []
    for geom_dict, value in shapes(mask, mask=mask, transform=transform):
        if value == 0:
            continue

        # Step 5: Convert to Shapely and validate
        geom = shape(geom_dict)
        geom = make_valid(geom)

        # Step 6: Simplify to reduce vertex count, then validate again
        if simplify_tolerance > 0:
            geom = geom.simplify(simplify_tolerance, preserve_topology=True)
            geom = make_valid(geom)

        # Step 7: Drop tiny polygons
        if geom.area < min_area_deg2:
            continue

        # Step 8: Clip to bbox if provided
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            geom = geom.intersection(
                shape(
                    {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [min_lon, min_lat],
                                [max_lon, min_lat],
                                [max_lon, max_lat],
                                [min_lon, max_lat],
                                [min_lon, min_lat],
                            ]
                        ],
                    }
                )
            )
            if geom.is_empty:
                continue

        # Step 9: Build the GeoJSON feature with required properties
        feature = geojson.Feature(
            geometry=mapping(geom),
            properties={
                "threshold": threshold,
                "product": product,
                "start_time": start_time,
                "end_time": end_time,
                "source_files": source_files,
                "created_at": created_at,
            },
        )
        features.append(feature)

    logger.info('Threshold %.2f": %d polygons', threshold, len(features))
    return features


def composite_max(arrays: list[np.ndarray]) -> np.ndarray:
    """Compute the per-cell maximum across multiple timesteps.

    Use this to build a swath from instantaneous MESH grids.
    Uses an incremental approach to avoid stacking all arrays into memory.
    """
    result = arrays[0].copy()
    for arr in arrays[1:]:
        np.fmax(result, arr, out=result)
    return result
