import sqlite3
from functools import partial, wraps
import json
import os
import pyproj
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry import shape
from shapely.ops import transform


BASE_DIR = os.path.dirname(__file__)

try_these = (
    "/usr/local/lib/mod_spatialite.dylib",
    "/usr/lib/x86_64-linux-gnu/mod_spatialite.so",
    "/usr/lib/x86_64-linux-gnu/libspatialite.so.5",
)


def insert_record(conn, id, geojson):
    poly = shape(geojson['geometry'])
    # Buffer by 5 miles - if you are within 5 miles of a lake you should
    # still hear about the lake monster!
    buffered_poly = buffer_polygon_in_meters(poly, 5 * 1600)
    if poly.geom_type == "Polygon":
        poly = MultiPolygon([poly])
    if buffered_poly.geom_type == "Polygon":
        buffered_poly = MultiPolygon([buffered_poly])
    conn.execute("""
        INSERT INTO cryptids (
            id, name, wikipedia_url, additional_url, description, copyright, first_sighted, last_sighted, geom, range)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, GeomFromText(?, 4326), GeomFromText(?, 4326))
    """, (
        id,
        geojson["properties"]["name"],
        geojson["properties"].get("wikipedia_url"),
        geojson["properties"].get("additional_url"),
        geojson["properties"]["description"],
        geojson["properties"].get("copyright"),
        geojson["properties"].get("first_sighted") or "",
        geojson["properties"].get("last_sighted") or "",
        buffered_poly.wkt,
        poly.wkt,
    ))


def build_database(dbpath="cryptids.db"):
    conn = sqlite3.connect(dbpath)
    # Enable Spatialite
    conn.enable_load_extension(True)
    for extension in try_these:
        if os.path.exists(extension):
            conn.load_extension(extension)
    conn.execute('select InitSpatialMetadata(1)')
    # Create the database table
    conn.execute('''
        create table cryptids (
            id integer primary key,
            name text,
            wikipedia_url text,
            additional_url text,
            description text,
            copyright text,
            first_sighted integer,
            last_sighted integer
        )
    ''')
    conn.execute("SELECT AddGeometryColumn('cryptids', 'geom', 4326, 'MULTIPOLYGON', 2);")
    conn.execute("SELECT CreateSpatialIndex('cryptids', 'geom');")
    conn.execute("SELECT AddGeometryColumn('cryptids', 'range', 4326, 'MULTIPOLYGON', 2);")
    conn.execute("SELECT CreateSpatialIndex('cryptids', 'range');")
    # Loop through and insert the records
    for filename in os.listdir(os.path.join(BASE_DIR, 'cryptids')):
        filepath = os.path.join(BASE_DIR, 'cryptids', filename)
        if filepath.endswith(".geojson"):
            id = filename.split(".")[0]
            insert_record(conn, id, json.load(open(filepath)))
    conn.commit()
    conn.close()


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
    build_database()
