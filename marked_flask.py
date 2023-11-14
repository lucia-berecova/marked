import os
import psycopg2
import logging
import json

from flask import Flask, request, jsonify, render_template

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

# PostgreSQL/PostGIS connection settings
DB_CONFIG = {
    'dbname': os.environ.get('DB_NAME'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'host': os.environ.get('DB_HOST')
}

def get_db_connection():
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if conn:
            return conn
@app.route('/station_coords', methods=['GET'])
def get_station_coords():
    station_name = request.args.get('name', default='', type=str)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Use PostGIS functions to extract longitude and latitude from the geom column
        cur.execute("""
            SELECT ST_Y(geom::geometry) AS latitude,
                   ST_X(geom::geometry) AS longitude
            FROM stations
            WHERE name ILIKE %s;
        """, ('%' + station_name + '%',))
        result = cur.fetchone()
        if result:
            coords = {'lat': result[0], 'lng': result[1]}
            return jsonify({'coordinates': coords})
        else:
            return jsonify({'error': 'Station not found'}), 404
    except Exception as e:
        app.logger.error("Error occurred: %s", str(e))
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/search_stations', methods=['GET'])
def get_stations():
    search_term = request.args.get('term', '')
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM stations WHERE name ILIKE %s;", ('%' + search_term + '%',))
        stations = cur.fetchall()
        # Convert to a list of names
        station_names = [station[0] for station in stations]
        return jsonify(station_names)
    except Exception as e:
        app.logger.error("Error occurred: %s", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/shortest_route', methods=['POST'])
def shortest_route():
    data = request.get_json()
    start_lat = data.get('start_lat')
    start_lon = data.get('start_lon')
    end_lat = data.get('end_lat')
    end_lon = data.get('end_lon')

    conn = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = """
        SELECT ST_AsGeoJSON(geom) AS route_geojson
        FROM shortest_path(%s, %s, %s, %s);
        """

        # Logging the query and input data
        app.logger.debug("Executing query: %s", query)
        app.logger.debug("With data: %s, %s, %s, %s", start_lon, start_lat, end_lon, end_lat)

        # Execute the query with the provided input data
        cur.execute(query, (start_lon, start_lat, end_lon, end_lat))

        route_geojson = cur.fetchone()
        if route_geojson is None:
            return jsonify({"error": "No route found"}), 404

        return jsonify(route_geojson=route_geojson[0])

    except Exception as e:
        app.logger.error("Error occurred: %s", str(e))  # log the error message
        return jsonify({"error": str(e)}), 500

    finally:
        if conn:
            conn.close()

@app.route('/all_routes')
def all_routes():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Query to get all routes
        cur.execute("SELECT ST_AsGeoJSON(geom) AS geojson FROM edinburgh;")
        routes = cur.fetchall()
        route_features = [{"type": "Feature", "geometry": json.loads(r[0])} for r in routes]

        # Query to get all stations with names
        cur.execute("SELECT ST_AsGeoJSON(geom) AS geojson, name FROM stations;")
        stations = cur.fetchall()
        station_features = [{"type": "Feature", "geometry": json.loads(s[0]), "properties": {"name": s[1]}} for s in stations]

        # Combine routes and stations into a single GeoJSON FeatureCollection
        all_features = route_features + station_features
        feature_collection = {"type": "FeatureCollection", "features": all_features}

        return jsonify(feature_collection)

    except Exception as e:
        app.logger.error("Error occurred: %s", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)