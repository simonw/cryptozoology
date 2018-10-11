import sqlite3
import json
import os
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry import shape

BASE_DIR = os.path.dirname(__file__)

try_these = (
    "/usr/local/lib/mod_spatialite.dylib",
    "/usr/lib/x86_64-linux-gnu/mod_spatialite.so",
    "/usr/lib/x86_64-linux-gnu/libspatialite.so.5",
)


def insert_record(conn, id, geojson):
    poly = shape(geojson['geometry'])
    if poly.geom_type == "Polygon":
        poly = MultiPolygon([poly])
    conn.execute("""
        INSERT INTO cryptids (
            id, name, wikipedia_url, additional_url, description, first_sighted, last_sighted, geom)
        VALUES(?, ?, ?, ?, ?, ?, ?, GeomFromText(?, 4326))
    """, (
        id,
        geojson["properties"]["name"],
        geojson["properties"]["wikipedia_url"],
        geojson["properties"].get("additional_url"),
        geojson["properties"]["description"],
        geojson["properties"]["first_sighted"],
        geojson["properties"]["last_sighted"],
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
            first_sighted integer,
            last_sighted integer
        )
    ''')
    conn.execute("SELECT AddGeometryColumn('cryptids', 'geom', 4326, 'MULTIPOLYGON', 2);")
    conn.execute("SELECT CreateSpatialIndex('cryptids', 'geom');")
    # Loop through and insert the records
    for filename in os.listdir(os.path.join(BASE_DIR, 'cryptids')):
        filepath = os.path.join(BASE_DIR, 'cryptids', filename)
        if filepath.endswith(".geojson"):
            id = filename.split(".")[0]
            insert_record(conn, id, json.load(open(filepath)))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    build_database()
