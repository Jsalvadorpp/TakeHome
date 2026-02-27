"""Convert MRMS grid data into GeoJSON swath polygons."""

import logging
from datetime import datetime, timezone

import geojson
import numpy as np
from rasterio.features import shapes
from rasterio.transform import Affine
from scipy.ndimage import gaussian_filter
from shapely.geometry import mapping, shape
from shapely.validation import make_valid

logger = logging.getLogger(__name__)

THRESHOLDS_INCHES = [0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50, 2.75]


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
    gaussian_sigma: int = 3,
    min_area_deg2: float = 1e-6,
) -> geojson.FeatureCollection:
    """Convert grid data to GeoJSON swath polygons at the given thresholds.

    Each threshold produces its own set of polygon features.

    How smoothing works:
      gaussian_sigma=5 blurs the raw MESH float values (~5 km radius) BEFORE
      thresholding. Because we blur the continuous values first and apply the
      threshold second, the mask boundary follows the smooth value gradient —
      this produces organic "teardrop" shapes like professional hail maps.

      Compare to blurring a binary mask (the old approach): that inflates the
      boundary outward by many kilometers because it spreads the 0→1 edge far
      from the original pixel. Blurring floats first causes the contour to move
      only a small amount (~1-2 km) even at sigma=5.
    """
    if source_files is None:
        source_files = []

    created_at = datetime.now(timezone.utc).isoformat()
    all_features = []

    # Replace NaN (missing radar data) with 0 before blurring.
    # NaN values would otherwise propagate through gaussian_filter and corrupt
    # large areas of the grid near coastlines and domain edges.
    data_filled = np.where(np.isnan(data), 0.0, data.astype(np.float32))

    # Blur the continuous MESH values once and reuse across all thresholds.
    if gaussian_sigma > 0:
        smoothed = gaussian_filter(data_filled, sigma=gaussian_sigma)
    else:
        smoothed = data_filled

    for threshold in sorted(thresholds, reverse=True):
        features = _polygonize_threshold(
            smoothed=smoothed,
            nan_mask=np.isnan(data),
            transform=transform,
            threshold=threshold,
            product=product,
            start_time=start_time,
            end_time=end_time,
            source_files=source_files,
            created_at=created_at,
            bbox=bbox,
            simplify_tolerance=simplify_tolerance,
            min_area_deg2=min_area_deg2,
        )
        all_features.extend(features)

    logger.info("Generated %d features across %d thresholds", len(all_features), len(thresholds))
    return geojson.FeatureCollection(all_features)


def _polygonize_threshold(
    smoothed: np.ndarray,
    nan_mask: np.ndarray,
    transform: Affine,
    threshold: float,
    product: str,
    start_time: str,
    end_time: str,
    source_files: list[str],
    created_at: str,
    bbox: tuple[float, float, float, float] | None,
    simplify_tolerance: float,
    min_area_deg2: float,
) -> list[geojson.Feature]:
    """Polygonize a single threshold and return a list of GeoJSON features.

    `smoothed` is the Gaussian-blurred MESH float grid (already computed in
    grid_to_swaths). Thresholding a smoothed float grid produces mask boundaries
    that follow the natural storm shape — smooth blobs that look like teardrops
    rather than connected squares.
    """
    # Step 1: Threshold the smoothed values. Exclude missing data cells.
    mask = (smoothed >= threshold) & ~nan_mask
    mask = mask.astype(np.uint8)

    if mask.sum() == 0:
        return []

    # Step 2: Polygonize — each disconnected region becomes its own polygon.
    features = []
    for geom_dict, value in shapes(mask, mask=mask, transform=transform):
        if value == 0:
            continue

        # Step 3: Convert to Shapely and validate.
        geom = shape(geom_dict)
        geom = make_valid(geom)

        # Step 4: Buffer round-trip to smooth pixel-grid staircase edges.
        # rasterio.shapes() still traces pixel boundaries even on a blurred mask.
        # Expand by 0.02° (~2 km) then contract by the same amount — this rounds
        # every pixel-corner into a smooth arc without changing the overall size.
        geom = geom.buffer(0.02).buffer(-0.02)
        geom = make_valid(geom)

        # Step 5: Simplify to reduce vertex count.
        # 0.005° ≈ 500 m — finer than the old 0.01° so curves stay smooth
        # rather than becoming angular straight-line segments between vertices.
        if simplify_tolerance > 0:
            geom = geom.simplify(simplify_tolerance, preserve_topology=True)
            geom = make_valid(geom)

        # Step 6: Drop tiny polygons (noise from isolated pixels).
        if geom.area < min_area_deg2:
            continue

        # Step 7: Clip to bbox if provided.
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            geom = geom.intersection(
                shape({
                    "type": "Polygon",
                    "coordinates": [[
                        [min_lon, min_lat], [max_lon, min_lat],
                        [max_lon, max_lat], [min_lon, max_lat],
                        [min_lon, min_lat],
                    ]],
                })
            )
            if geom.is_empty:
                continue

        # Step 8: Build the GeoJSON feature with required properties.
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