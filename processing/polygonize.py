"""Convert MRMS grid data into GeoJSON swath polygons."""

import logging
from datetime import datetime, timezone

import geojson
import numpy as np
from rasterio.features import shapes
from rasterio.transform import Affine
from scipy.ndimage import binary_closing
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
    smooth_tolerance: float = 0.03,
    min_area_deg2: float = 1e-6,
) -> geojson.FeatureCollection:
    """Convert grid data to GeoJSON swath polygons at the given thresholds.

    Each threshold produces its own set of polygon features.
    All geometries are smoothed, validated, and simplified.

    smooth_tolerance controls how much corner-rounding is applied (in degrees).
    A value of 0.01 (~1 km) rounds blocky raster edges into smooth organic curves.
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
            smooth_tolerance=smooth_tolerance,
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
    smooth_tolerance: float,
    min_area_deg2: float,
) -> list[geojson.Feature]:
    """Polygonize a single threshold and return a list of GeoJSON features."""
    # Step 1: Binary mask
    mask = data >= threshold
    mask = mask & ~np.isnan(data)

    # Step 2: Morphological cleanup (close small gaps within existing swaths)
    mask = binary_closing(mask, structure=np.ones((2, 2)))

    # Convert to uint8 for rasterio
    mask = mask.astype(np.uint8)

    if mask.sum() == 0:
        return []

    # Step 3: Polygonize
    features = []
    for geom_dict, value in shapes(mask, mask=mask, transform=transform):
        if value == 0:
            continue

        # Step 4: Convert to Shapely and validate
        geom = shape(geom_dict)
        geom = make_valid(geom)

        # Step 5: Smooth edges — expand outward then contract by the same amount.
        # This rounds off the blocky right-angle corners that come from polygonizing
        # a raster grid. Result: soft, organic curves instead of square edges.
        # Example: smooth_tolerance=0.01 expands ~1 km, then shrinks back ~1 km.
        if smooth_tolerance > 0:
            geom = geom.buffer(smooth_tolerance).buffer(-smooth_tolerance)
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
