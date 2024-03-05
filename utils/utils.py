import psycopg2
from database.db import Database
from database.queries import ALL_QUERIES
from shapely import Point, LineString
from shapely.wkt import loads
import geopandas as gdp
from graph.graph import Node, Graph
import re

QUERIES = {
    'nodes': """
        INSERT INTO nodes (name, point_geom)
        VALUES (%s, ST_GeomFromText(%s))
        """,

    'weight': """
        INSERT INTO weights (from_node_id, to_node_id, distance)
        VALUES (%s, %s, %s)
        """,

    'edges': """
        INSERT INTO edges (node_id, neighbors)
        VALUES (%s, to_jsonb( %s ))
        """
}


class NodeKeyGenerator:

    def __init__(self):
        self.counter = 1
        self.key_map = {}

    def generate_node_key(self, data):
        if data in self.key_map:
            return self.key_map[data]

        key = f"n{self.counter}"
        self.counter += 1
        self.key_map[data] = key
        return key


def extract_node_id(node_label_string):
    match = re.search(r'\d+', node_label_string)
    return int(match.group()) if match else None


def init_db(db):
    try:
        db.execute_query(ALL_QUERIES)
    except psycopg2.Error as e:
        print('Could not Initialize database', e)
    else:
        print("DB initialized")


def populate_db(graph):
    db = Database(dbname='routes', user='postgres', host='localhost')
    connected = db.connect()

    if connected:
        init_db(db)
        # init_db(db)

        for node in graph.nodes:
            x, y, label = graph.nodes[node].x, graph.nodes[node].y, graph.nodes[node].label
            point = f'POINT({x} {y})'
            edges = [extract_node_id(n) for n in graph.edges[label]]

            db.execute_query(QUERIES['nodes'],
                             (label, point)
                             )

            db.execute_query(
                QUERIES['edges'],
                (
                    extract_node_id(label),
                    edges
                )
            )

        for weight in graph.weights:
            db.execute_query(
                QUERIES['weight'],
                (
                    extract_node_id(weight[0]),
                    extract_node_id(weight[-1]),
                    graph.weights[weight]
                )
            )

    db.close()


def read_to_graph(file_name, should_densify_segments=False, distance=2):
    new_graph = Graph()
    node_key_generator = NodeKeyGenerator()

    gdf = gdp.read_file(file_name)

    for index, current_row in gdf.iterrows():

        if should_densify_segments:
            current_segment = list(line_densify(polyline=current_row.geometry, step_dist=distance).coords)
        else:
            current_segment = list(current_row.geometry.coords)
            # print(current_segment)

        prev_coords_pair = None
        for (x, y) in current_segment:
            if prev_coords_pair is not None:
                x_from, y_from = prev_coords_pair
                from_node = Node(
                    x=x_from,
                    y=y_from,
                    label=node_key_generator.generate_node_key(f"{x_from}-{y_from}")
                )

                to_node = Node(
                    x=x,
                    y=y,
                    label=node_key_generator.generate_node_key(f"{x}-{y}")
                )

                new_graph.add_node(from_node=from_node, to_node=to_node,
                                   weight=new_graph.get_weight(from_node=from_node,
                                                               to_node=to_node))
            prev_coords_pair = x, y

    return new_graph


def line_densify(polyline, step_dist):
    coords = list(polyline.coords)
    segments = list(zip(coords[:-1], coords[1:]))
    dens_coords = []
    for i, segment in enumerate(segments):
        a, b = segment
        seg_coords = segment_densify(a, b, step_dist)
        dens_coords.extend(seg_coords if i == 0 else seg_coords[1:])
    return LineString(dens_coords)


def segment_densify(pt_a, pt_b, step_dist):
    pt_b_geom = Point(pt_b)
    geom = LineString([pt_a, pt_b])
    inter_dist = step_dist
    dense_coords = [pt_a]
    while inter_dist < geom.length:
        pt = geom.interpolate(inter_dist)
        gap = pt.distance(pt_b_geom)
        if gap > step_dist:
            dense_coords.append(pt)
        inter_dist += step_dist
    dense_coords.append(pt_b)
    return dense_coords


# Example for segment densify
if __name__ == '__main__':
    wkt = "LINESTRING ( 35 758, 1480 729 )"
    geom = line_densify(loads(wkt), 50)
    print(geom)
