"""
Start with KML of Bigfoot sightings from http://www.bfro.net/

Assume they have a range of 15 miles - so buffer each of those sighting
locations by 15 miles.

Combine it into a single multipolygon using Shapely.
"""
import requests, zipfile, io
from xml.dom import minidom
from functools import partial, wraps
import json

import pyproj
from shapely.ops import transform, cascaded_union
from shapely.geometry import shape, mapping
from kml2geojson import build_geometry


def derive_bigfoot_range():
    kmlz = requests.get("http://www.bfro.net/app/AllReportsKMZ.aspx").content
    zf = zipfile.ZipFile(io.BytesIO(kmlz))
    kml = zf.open("doc.kml").read()
    doc = minidom.parseString(kml)
    buffered_polygons = []
    for folder in doc.getElementsByTagName("Folder"):
        try:
            geoms = build_geometry(folder)["geoms"]
            geom = geoms[0]
            # Buffer by 15 miles (according to Bigfoot Discovery Museum chap)
            buffered_polygons.append(buffer_polygon_in_meters(shape(geom), 24140))
        except Exception as e:
            print(e)
    valid_buffered_polygons = [b for b in buffered_polygons if b.is_valid]
    combined = cascaded_union(valid_buffered_polygons)
    open("bigfoot.geojson", "w").write(json.dumps(mapping(combined)))


wgs84 = pyproj.Proj("+init=EPSG:4326")


def process_wgs84_in_meters(fn):
    # Given a function which takes a polygon as the
    # first argument, this decorator ensures that
    # the polygon will first be transformed to a custom
    # aeqd projection centered around the center of that
    # polygon, which operates in meters. This newly
    # transformed polygon will be passed to the real
    # function, which can then operate on it using meters
    # as the units. It can return a polygon-in-meters
    # which will then be transformed back to wgs84
    @wraps(fn)
    def wrapper(polygon, *args, **kwargs):
        # Custom aeqd projection centered on the polygon centroid
        centroid = polygon.centroid
        custom_projection = pyproj.Proj(
            "+proj=aeqd +lat_0=%s +lon_0=%s +units=m" % (centroid.y, centroid.x)
        )
        project = partial(pyproj.transform, wgs84, custom_projection)
        polygon_in_m = transform(project, polygon)
        # Actually run the decorated function
        resulting_polygon_in_m = fn(polygon_in_m, *args, **kwargs)
        # Convert back to wgs84 again
        reverse_project = partial(pyproj.transform, custom_projection, wgs84)
        return transform(reverse_project, resulting_polygon_in_m)

    return wrapper


@process_wgs84_in_meters
def buffer_polygon_in_meters(polygon, meters):
    # Given a shapely polygon with its points
    # defined using lat/lon, return a polygon
    # representing the input expanded in all
    # directions by X meters.
    return polygon.buffer(meters)


if __name__ == "__main__":
    derive_bigfoot_range()
