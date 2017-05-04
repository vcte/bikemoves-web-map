# Web map server #

# import flask libraries
from flask import Flask
from flask import render_template
from flask import request

# import general libraries
from math import *
import os
import time
import json

from util import *

# set up flask app
app = Flask(__name__)

# global data
trail_data = read_json("static/data/bike_trail.geojson")
point_data = read_json("static/data/point.geojson")
racks = read_tsv("static/data/bike_racks.csv")

# calculate log of aadt data
street_data = read_json("static/data/street.geojson")
aadt_data = [(int(log(feat["properties"]["AADT"] + 1)),
              feat["geometry"]["coordinates"])
             for feat in street_data["features"]]
del street_data

# names of alternative routes
alt_route_types = ["clean_data",
                   "shortest_route",
                   "second_shortest_route",
                   "minimum_intersections_route",
                   "speed_route"]

# populate the data structure, such that
# map_match_data[route_type][trip_id] = list of coordinates of paths
route_data = []
for route_type in alt_route_types:
    route_json = read_json("static/data/" + route_type + ".geojson")
    
    alt_route_data = []
    for features in route_json["features"]:
        trip_id = int(features["properties"]["TRIP_ID"])
        coords  = features["geometry"]["coordinates"]

        # ensure that coordinates are in triply nested format
        if features["geometry"]["type"] == "LineString":
            coords = [coords]

        # extend size of list, so that list is at least trip_id + 1 long
        size_difference = trip_id - len(alt_route_data) + 1
        alt_route_data.extend([None for _ in range(size_difference)])
        
        alt_route_data[trip_id] = coords
    route_data.append(alt_route_data)

# mapping from location type ID to the name of the location type
location_types = ["?", "Home", "Work", "K-12 School",
                  "University", "Shopping", "Other"]

# default url
@app.route("/", defaults = {"trip_id" : None})
@app.route("/<int:trip_id>")
def main(trip_id):
    # load trips and convert the destination types
    trips = read_tsv("static/data/trip.csv", header = True)

    trip_fid = 0
    for i, trip in list(enumerate(trips)):
        # interpret the origin / destination type codes
        trips[i][2] = location_types[int(trips[i][2])]
        trips[i][3] = location_types[int(trips[i][3])]

        # track the position of the trip in the list
        if trip[1] == str(trip_id):
            trip_fid = trip[0]

    # load route data for all alternative route variants
    all_paths = []
    all_types = []
    if trip_id != None:
        for route_type, alt_route_data in zip(alt_route_types, route_data):
            coords = alt_route_data[int(trip_id)]
            if coords != None:
                # flatten and combine data, so that it represents line segments
                paths = [line for path in coords for line in path]
                paths = list(zip(paths, paths[1:]))
                
                all_paths.append(paths)
                all_types.append(route_type)

    # process point data
    points = []
    inf = float("inf")
    lng_prev, lat_prev, sec_prev = None, None, None
    lng_max, lng_min, lat_max, lat_min = -inf, inf, -inf, inf

    # assumes that within a trip, points are ordered by time
    for i, feature in enumerate(point_data["features"]):
        if str(feature["properties"]["trip_id"]) == str(trip_id):
            # gather attributes of GPS point
            acc = round(feature["properties"]["accuracy"], 3)
            alt = feature["properties"]["altitude"]
            date = feature["properties"]["time"]
            sec = time.mktime(time.strptime(date, "%Y/%m/%d %H:%M:%S"))
            tme = date.partition(" ")[2]
            lng, lat = feature["geometry"]["coordinates"]

            # calculate velocity
            if lat_prev != None and lng_prev != None:
                vel = round(haversine(lat, lng, lat_prev, lng_prev) /
                            (sec - sec_prev + 0.00001), 3)
            else:
                vel = 0.0

            # add coordinates of last point, so that line can be drawn btwn them
            points.append([i, lat, lng, lat_prev, lng_prev, tme, alt, acc, vel])
            lat_prev, lng_prev, sec_prev = lat, lng, sec

            # determine bounding box for trip
            lng_max = max(lng_max, lng); lng_min = min(lng_min, lng)
            lat_max = max(lat_max, lat); lat_min = min(lat_min, lat)

    # gather trail data which intersects bounding box of trip
    trails = []
    for feature in trail_data["features"]:
        # gather attributes of trail
        trail_type = feature["properties"]["path_type"]
        trail_name = feature["properties"]["name"]
        trail_coord = feature["geometry"]["coordinates"]

        # ensure that coordinates are in triply nested format
        if nest_depth(trail_coord) < 3:
            trail_coord = [trail_coord]

        # determine if any part of the trail intersects w/ bounding box
        if any([lng_min < lng < lng_max and lat_min < lat < lat_max
                for path in trail_coord for lng, lat in path]):
            trail_lines = []
            for path in trail_coord:
                trail_lines += list(zip(path, path[1:]))
            trails.append((trail_type, trail_name, trail_lines))

    # gather traffic data which intersects bounding box of trip
    trip_aadt = []
    mix = lambda x, y, p: p * x + (1 - p) * y
    for a, coords in aadt_data:
        # determine if any part of road intersects w/ bounding box
        if any([lng_min < lng < lng_max and lat_min < lat < lat_max
                for lng, lat, _ in coords]):
            for coord_1, coord_2 in zip(coords, coords[1:]):
                # add 10 pts evenly spaced between the endpoints,
                # so that heatmap will be densely populated
                for i in range(10):
                    trip_aadt.append((mix(coord_1[1], coord_2[1], i / 10.0),
                                      mix(coord_1[0], coord_2[0], i / 10.0), a))
    
    return render_template("web_map.html", trips = trips, trip_id=str(trip_id),
                           trip_fid = trip_fid, points = points,
                           all_paths = all_paths, mm_types = all_types,
                           trails = trails, aadt = trip_aadt, racks = racks)

# IDEAS:
# give home / destination markers a different color / shape
# frequency grid heatmap, normalize for each user
# interpolate velocity over previous and next point

if __name__ == "__main__":
    """main function - run web app"""
    app.run()
