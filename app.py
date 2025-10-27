# app.py
import streamlit as st
import networkx as nx
import folium
from streamlit_folium import st_folium
from folium.plugins import AntPath

st.set_page_config(page_title="Smart Delivery Route Planner 🚚", layout="wide")
st.title("🚚 Smart Delivery Route Planner")
st.markdown("Interactive shortest-route planner — stable UI + animated route. (Dijkstra under the hood)")

# ------------------ Helpers ------------------
def init_state():
    if "locations" not in st.session_state:
        st.session_state.locations = []  # list of dicts: {"name":..., "lat":..., "lon":...}
    if "edges" not in st.session_state:
        st.session_state.edges = []      # list of tuples: (u_name, v_name, weight)

def build_graph():
    G = nx.Graph()
    for loc in st.session_state.locations:
        G.add_node(loc["name"], pos=(loc["lat"], loc["lon"]))
    for (u, v, w) in st.session_state.edges:
        # add or update an edge (undirected)
        G.add_edge(u, v, weight=w)
    return G

def coords_by_name(name):
    for loc in st.session_state.locations:
        if loc["name"] == name:
            return (loc["lat"], loc["lon"])
    return None

# initialize session state containers
init_state()

# ------------------ SIDEBAR: Configuration Form ------------------
with st.sidebar.form(key="config_form"):
    st.header("📍 Configure Map")
    num_locations = st.number_input("Number of locations", min_value=2, max_value=20, value=max(3, len(st.session_state.locations)), step=1)
    
    # Collect location inputs
    locs_temp = []
    st.markdown("**Locations (give unique names)**")
    for i in range(int(num_locations)):
        default_name = f"Point{i+1}"
        # If session has that index already, show its saved values as defaults
        if i < len(st.session_state.locations):
            existing = st.session_state.locations[i]
            name = st.text_input(f"Name {i+1}", value=existing["name"], key=f"name_{i}")
            lat = st.number_input(f"Latitude {i+1}", value=existing["lat"], key=f"lat_{i}")
            lon = st.number_input(f"Longitude {i+1}", value=existing["lon"], key=f"lon_{i}")
        else:
            name = st.text_input(f"Name {i+1}", value=default_name, key=f"name_{i}")
            lat = st.number_input(f"Latitude {i+1}", value=19.0760 + i*0.005, key=f"lat_{i}")
            lon = st.number_input(f"Longitude {i+1}", value=72.8777 + i*0.005, key=f"lon_{i}")
        locs_temp.append({"name": name.strip(), "lat": float(lat), "lon": float(lon)})

    st.markdown("---")
    st.markdown("**Roads / Edges**")
    num_edges = st.number_input("Number of roads (edges) to define", min_value=1, max_value=100, value=max(1, len(st.session_state.edges)), step=1)
    edges_temp = []
    options_names = [l["name"] for l in locs_temp if l["name"] != ""]
    if not options_names:
        st.warning("Provide at least one valid location name before creating roads.")
    for i in range(int(num_edges)):
        u = st.selectbox(f"From (road {i+1})", options=options_names, key=f"edge_u_{i}")
        v = st.selectbox(f"To (road {i+1})", options=options_names, key=f"edge_v_{i}")
        w = st.number_input(f"Distance (units) for road {i+1}", min_value=1.0, value=1.0, key=f"edge_w_{i}")
        edges_temp.append((u, v, float(w)))

    submit_config = st.form_submit_button("💾 Save Configuration")

# When configuration is saved, validate and store in session state
if submit_config:
    # Validate unique names and non-empty
    names = [l["name"] for l in locs_temp]
    if any(n == "" for n in names):
        st.sidebar.error("Location names cannot be empty. Fix the empty names and save again.")
    elif len(set(names)) != len(names):
        st.sidebar.error("Location names must be unique. Use distinct names.")
    else:
        # Validate edges: no self-loops
        bad_edges = [e for e in edges_temp if e[0] == e[1]]
        if bad_edges:
            st.sidebar.error("Roads cannot connect a location to itself. Fix edges.")
        else:
            st.session_state.locations = locs_temp
            # filter edges to only those with endpoints present (just in case)
            filtered_edges = [e for e in edges_temp if e[0] in names and e[1] in names]
            st.session_state.edges = filtered_edges
            st.sidebar.success("Configuration saved. You can now find routes.")

# ------------------ MAIN AREA ------------------
st.subheader("Map & Route Controls")

# If no locations saved, show instruction
if len(st.session_state.locations) == 0:
    st.info("Use the sidebar to add locations and roads, then click 'Save Configuration'.")
    st.stop()

# Show quick overview
col1, col2 = st.columns([1, 1])
with col1:
    st.markdown(f"**Locations ({len(st.session_state.locations)}):**")
    for loc in st.session_state.locations:
        st.write(f"- {loc['name']}  (lat: {loc['lat']:.5f}, lon: {loc['lon']:.5f})")
with col2:
    st.markdown(f"**Roads ({len(st.session_state.edges)}):**")
    for u, v, w in st.session_state.edges:
        st.write(f"- {u} ↔ {v}  :  {w} units")

# Choose start and end from saved locations
names_saved = [l["name"] for l in st.session_state.locations]
start = st.selectbox("🏠 Warehouse (start)", options=names_saved, index=0)
end = st.selectbox("📦 Destination (end)", options=names_saved, index=min(1, len(names_saved)-1))

# Button to compute
compute = st.button("🚀 Find Shortest Route")

# Build graph object
G = build_graph()

# If compute pressed, run and show result (uses session state so reruns safe)
if compute:
    if start == end:
        st.warning("Start and end are the same location — distance is 0.")
    else:
        if not G.has_node(start) or not G.has_node(end):
            st.error("Start or end node missing in the graph. Re-save configuration.")
        else:
            try:
                path = nx.shortest_path(G, source=start, target=end, weight="weight")
                total_distance = nx.shortest_path_length(G, source=start, target=end, weight="weight")

                st.success(f"**Shortest Route:** {' → '.join(path)}")
                st.info(f"**Total Distance:** {total_distance} units")

                # Map: center around average coords
                avg_lat = sum(l["lat"] for l in st.session_state.locations) / len(st.session_state.locations)
                avg_lon = sum(l["lon"] for l in st.session_state.locations) / len(st.session_state.locations)
                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)

                # Add all nodes
                for loc in st.session_state.locations:
                    folium.Marker([loc["lat"], loc["lon"]], popup=loc["name"],
                                  icon=folium.Icon(color="blue", icon="info-sign")).add_to(m)

                # Draw all edges (light)
                for u, v, w in st.session_state.edges:
                    c1 = coords_by_name(u)
                    c2 = coords_by_name(v)
                    if c1 and c2:
                        folium.PolyLine(locations=[c1, c2], weight=2, color="#888", opacity=0.6).add_to(m)
                        # mid label
                        mid = [(c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2]
                        folium.map.Marker(mid, icon=folium.DivIcon(html=f"<div style='font-size:10px'>{w}</div>")).add_to(m)

                # Path coordinates
                path_coords = [coords_by_name(node) for node in path if coords_by_name(node) is not None]

                # Animated path (AntPath)
                AntPath(path_coords, color="#00cc44", weight=6, delay=1000).add_to(m)
                # Start & End markers larger
                folium.Marker(path_coords[0], popup="Start: " + start, icon=folium.Icon(color="red", icon="home")).add_to(m)
                folium.Marker(path_coords[-1], popup="End: " + end, icon=folium.Icon(color="green", icon="flag")).add_to(m)

                st_folium(m, width=1000, height=600)

            except nx.NetworkXNoPath:
                st.error("❌ No path exists between the selected nodes with the given roads.")
            except Exception as ex:
                st.error(f"An unexpected error occurred: {ex}")
else:
    # show map preview with all nodes and edges but no highlighted route
    avg_lat = sum(l["lat"] for l in st.session_state.locations) / len(st.session_state.locations)
    avg_lon = sum(l["lon"] for l in st.session_state.locations) / len(st.session_state.locations)
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)
    for loc in st.session_state.locations:
        folium.Marker([loc["lat"], loc["lon"]], popup=loc["name"],
                      icon=folium.Icon(color="blue", icon="info-sign")).add_to(m)
    for u, v, w in st.session_state.edges:
        c1 = coords_by_name(u)
        c2 = coords_by_name(v)
        if c1 and c2:
            folium.PolyLine(locations=[c1, c2], weight=2, color="#888", opacity=0.6).add_to(m)
    st_folium(m, width=1000, height=500)
